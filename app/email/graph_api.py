"""
Tier 1 — Microsoft Graph API email access via MSAL OAuth2.

Uses the device-code flow so no redirect server is needed.
Token cache is persisted to data/tokens/graph_token.json.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import msal
import requests

from app.config import TOKENS_DIR, ATTACHMENTS_DIR

log = logging.getLogger(__name__)

GRAPH_SCOPES = ["Mail.Read"]
AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphEmailClient:
    def __init__(self, client_id: str, tenant_id: str):
        self.client_id = client_id
        self.tenant_id = tenant_id
        self._cache_path = TOKENS_DIR / "graph_token.json"
        self._cache = self._load_cache()
        self._app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=AUTHORITY_TEMPLATE.format(tenant_id=self.tenant_id),
            token_cache=self._cache,
        )

    # ------------------------------------------------------------------
    # Token cache persistence
    # ------------------------------------------------------------------

    def _load_cache(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if self._cache_path.exists():
            cache.deserialize(self._cache_path.read_text(encoding="utf-8"))
        return cache

    def _save_cache(self):
        if self._cache.has_state_changed:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(self._cache.serialize(), encoding="utf-8")

    # ------------------------------------------------------------------
    # Token acquisition
    # ------------------------------------------------------------------

    def _get_token(self) -> Optional[str]:
        """Return a valid access token, refreshing silently if possible."""
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]

        # Need interactive auth (device-code flow — opens browser)
        flow = self._app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError("Could not initiate device code flow: " + str(flow))

        log.info("Device code flow: %s", flow.get("message"))
        # The message contains the URL and code to enter
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            self._save_cache()
            return result["access_token"]

        raise RuntimeError("Authentication failed: " + result.get("error_description", str(result)))

    def get_device_flow_message(self) -> dict:
        """
        Start device-code flow and return the user-facing message.
        Call complete_device_flow() after the user authenticates.
        """
        flow = self._app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError("Could not initiate device code flow")
        self._pending_flow = flow
        return {
            "message": flow["message"],
            "verification_uri": flow.get("verification_uri", "https://microsoft.com/devicelogin"),
            "user_code": flow["user_code"],
        }

    def complete_device_flow(self) -> bool:
        """Complete the pending device-code flow. Returns True on success."""
        if not hasattr(self, "_pending_flow"):
            return False
        result = self._app.acquire_token_by_device_flow(self._pending_flow)
        if "access_token" in result:
            self._save_cache()
            return True
        return False

    # ------------------------------------------------------------------
    # Connectivity test
    # ------------------------------------------------------------------

    def test_connection(self) -> tuple[bool, str]:
        """Test connection by fetching /me profile. Returns (ok, message)."""
        try:
            token = self._get_token()
            resp = requests.get(
                f"{GRAPH_BASE}/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("displayName", data.get("mail", "Unknown"))
                return True, f"Connected as {name}"
            return False, f"Graph API returned HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Email fetching
    # ------------------------------------------------------------------

    def fetch_emails(self, since_date: datetime, payor_profile=None) -> list[dict]:
        """
        Fetch emails from the Inbox within a date window.
        Returns a list of normalised email dicts.
        """
        try:
            token = self._get_token()
        except Exception as e:
            log.warning("GraphAPI token error: %s", e)
            raise

        headers = {"Authorization": f"Bearer {token}"}

        # Date range: since_date (already pre-widened by caller)
        since_str = since_date.strftime("%Y-%m-%dT00:00:00Z")

        params = {
            "$filter": f"receivedDateTime ge {since_str}",
            "$select": "id,subject,from,receivedDateTime,body,hasAttachments",
            "$top": 100,
            "$orderby": "receivedDateTime desc",
        }

        # Narrow by sender if payor profile specifies one
        if payor_profile:
            sender_email = payor_profile.get("sender_email") or ""
            sender_domain = payor_profile.get("sender_domain") or ""
            if sender_email:
                params["$filter"] += f" and from/emailAddress/address eq '{sender_email}'"
            elif sender_domain:
                # Graph doesn't support ends-with filter directly; fetch broadly and filter locally
                pass

        resp = requests.get(
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages",
            headers=headers,
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Graph API error {resp.status_code}: {resp.text[:300]}")

        messages = resp.json().get("value", [])
        results = []
        for msg in messages:
            email_dict = self._normalise_message(msg, headers, payor_profile)
            if email_dict:
                results.append(email_dict)
        return results

    def _normalise_message(self, msg: dict, headers: dict, payor_profile) -> Optional[dict]:
        """Convert a Graph API message object to our internal email dict."""
        from_addr = msg.get("from", {}).get("emailAddress", {})
        sender = from_addr.get("address", "")
        domain = sender.split("@")[-1].lower() if "@" in sender else ""

        # Domain filter (applied locally if we couldn't do it server-side)
        if payor_profile:
            prof_domain = (payor_profile.get("sender_domain") or "").lower()
            prof_email  = (payor_profile.get("sender_email") or "").lower()
            if prof_email and sender.lower() != prof_email:
                return None
            if prof_domain and not domain.endswith(prof_domain) and prof_email == "":
                return None

        body_content = msg.get("body", {}).get("content", "")
        body_type    = msg.get("body", {}).get("contentType", "text")

        attachments = []
        if msg.get("hasAttachments"):
            attachments = self._fetch_attachments(msg["id"], headers)

        return {
            "message_id":    msg["id"],
            "subject":       msg.get("subject", ""),
            "sender":        sender,
            "sender_domain": domain,
            "received_date": msg.get("receivedDateTime", ""),
            "body_html":     body_content if body_type == "html" else "",
            "body_text":     body_content if body_type == "text" else "",
            "attachments":   attachments,
            "source_tier":   "graph",
        }

    def _fetch_attachments(self, message_id: str, headers: dict) -> list[dict]:
        """Download attachments and save to data/attachments/. Returns list of {name, path, content_type}."""
        resp = requests.get(
            f"{GRAPH_BASE}/me/messages/{message_id}/attachments",
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            return []

        items = resp.json().get("value", [])
        results = []
        for att in items:
            if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue
            import base64
            content_b64 = att.get("contentBytes", "")
            if not content_b64:
                continue
            content = base64.b64decode(content_b64)
            fname = att.get("name", "attachment")
            save_path = ATTACHMENTS_DIR / f"{message_id}_{fname}"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(content)
            results.append({
                "name": fname,
                "path": str(save_path),
                "content_type": att.get("contentType", "application/octet-stream"),
            })
        return results
