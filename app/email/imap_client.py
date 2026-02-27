"""
Tier 2 — IMAP email access.

Uses imaplib (Python standard library) with SSL on port 993.
Passwords are stored encrypted via app.crypto and decrypted only in-memory.
"""
import email
import imaplib
import logging
import socket
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path
from typing import Optional

from app.config import IMAP_HOST, IMAP_PORT, ATTACHMENTS_DIR

log = logging.getLogger(__name__)


class ImapClient:

    def __init__(self, email_addr: str, password: str):
        self.email_addr = email_addr
        self.password = password

    @staticmethod
    def test_connection(email_addr: str, password: str) -> dict:
        """
        Attempt a live IMAP connection and authentication.
        Returns:
          {"ok": bool, "error_type": None|"refused"|"auth"|"timeout", "message": str}
        """
        try:
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=10)
        except ConnectionRefusedError:
            return {
                "ok": False,
                "error_type": "refused",
                "message": f"Connection refused to {IMAP_HOST}:{IMAP_PORT}. IMAP may be disabled at the tenant level.",
            }
        except socket.timeout:
            return {
                "ok": False,
                "error_type": "timeout",
                "message": f"Connection timed out to {IMAP_HOST}:{IMAP_PORT}. Port 993 may be blocked by a firewall.",
            }
        except OSError as e:
            return {
                "ok": False,
                "error_type": "timeout",
                "message": f"Network error: {e}",
            }

        try:
            conn.login(email_addr, password)
            conn.logout()
            return {"ok": True, "error_type": None, "message": "IMAP connection and authentication successful."}
        except imaplib.IMAP4.error as e:
            msg = str(e)
            if "AUTHENTICATIONFAILED" in msg.upper() or "Invalid credentials" in msg:
                return {
                    "ok": False,
                    "error_type": "auth",
                    "message": "Authentication failed. Check your email address and password. If MFA is enabled, you may need an App Password.",
                }
            return {"ok": False, "error_type": "auth", "message": f"IMAP login error: {msg}"}

    def fetch_emails(self, since_date: datetime, payor_profile: Optional[dict] = None) -> list[dict]:
        """Fetch emails since since_date matching payor_profile. Returns normalised dicts."""
        try:
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=30)
            conn.login(self.email_addr, self.password)
        except Exception as e:
            log.warning("IMAP connect/login failed: %s", e)
            raise

        try:
            conn.select("INBOX")
            date_str = since_date.strftime("%d-%b-%Y")
            search_criteria = [f'SINCE "{date_str}"']

            if payor_profile:
                sender_email = (payor_profile.get("sender_email") or "").strip()
                if sender_email:
                    search_criteria.append(f'FROM "{sender_email}"')
                else:
                    sender_domain = (payor_profile.get("sender_domain") or "").strip()
                    if sender_domain:
                        search_criteria.append(f'FROM "@{sender_domain}"')

                keywords = payor_profile.get("subject_keywords") or []
                if isinstance(keywords, str):
                    import json
                    try:
                        keywords = json.loads(keywords)
                    except Exception:
                        keywords = []
                if keywords:
                    search_criteria.append(f'SUBJECT "{keywords[0]}"')

            criteria_str = " ".join(f"({c})" if " " in c else c for c in search_criteria)
            _typ, data = conn.search(None, criteria_str)

            msg_ids = data[0].split() if data[0] else []
            results = []
            for mid in msg_ids:
                try:
                    _typ, raw = conn.fetch(mid, "(RFC822)")
                    if raw and raw[0]:
                        parsed = self._parse_message(raw[0][1])
                        if parsed:
                            results.append(parsed)
                except Exception as e:
                    log.warning("Error fetching IMAP message %s: %s", mid, e)

            return results
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _parse_message(self, raw_bytes: bytes) -> Optional[dict]:
        """Parse a raw RFC822 email into our normalised dict format."""
        try:
            msg = email.message_from_bytes(raw_bytes)
        except Exception as e:
            log.warning("Failed to parse email: %s", e)
            return None

        sender = self._decode_header_value(msg.get("From", ""))
        subject = self._decode_header_value(msg.get("Subject", ""))
        date_str = msg.get("Date", "")
        message_id = msg.get("Message-ID", str(hash(raw_bytes)))

        # Extract sender address
        import re
        addr_match = re.search(r"<([^>]+)>", sender)
        sender_addr = addr_match.group(1) if addr_match else sender.strip()
        domain = sender_addr.split("@")[-1].lower() if "@" in sender_addr else ""

        body_text = ""
        body_html = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = part.get_content_disposition() or ""
                if ct == "text/plain" and "attachment" not in cd:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                elif ct == "text/html" and "attachment" not in cd:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                elif "attachment" in cd or (ct not in ("text/plain", "text/html", "multipart/alternative", "multipart/mixed")):
                    fname = part.get_filename()
                    if fname:
                        fname = self._decode_header_value(fname)
                        payload = part.get_payload(decode=True)
                        if payload:
                            save_path = ATTACHMENTS_DIR / f"{message_id.strip('<>')}_{fname}"
                            save_path.parent.mkdir(parents=True, exist_ok=True)
                            save_path.write_bytes(payload)
                            attachments.append({
                                "name": fname,
                                "path": str(save_path),
                                "content_type": ct,
                            })
        else:
            payload = msg.get_payload(decode=True)
            ct = msg.get_content_type()
            if payload:
                text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                if ct == "text/html":
                    body_html = text
                else:
                    body_text = text

        return {
            "message_id":    message_id,
            "subject":       subject,
            "sender":        sender_addr,
            "sender_domain": domain,
            "received_date": date_str,
            "body_html":     body_html,
            "body_text":     body_text,
            "attachments":   attachments,
            "source_tier":   "imap",
        }

    @staticmethod
    def _decode_header_value(value: str) -> str:
        """Decode potentially encoded email header values."""
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)
