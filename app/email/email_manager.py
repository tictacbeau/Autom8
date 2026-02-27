"""
Email Manager — orchestrates the three email access tiers.

Tries each tier in configured priority order and falls back automatically.
Reports which tier is currently active.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import DEFAULT_TIER_ORDER, TIER_GRAPH, TIER_IMAP, TIER_FOLDER, LOOKBACK_DAYS_DEFAULT
from app.database import get_config, get_db, now_iso

log = logging.getLogger(__name__)

# Shared in-memory record of the currently active tier (for UI display)
_active_tier: str = "none"


def get_active_tier() -> str:
    return _active_tier


def set_active_tier(tier: str):
    global _active_tier
    _active_tier = tier


def scan_emails_for_deposit(deposit: dict, payor_profile: Optional[dict]) -> list[dict]:
    """
    Try each configured email tier in priority order.
    Returns a list of email dicts from the first tier that succeeds.
    Raises if all tiers fail.
    """
    lookback = int(get_config("lookback_days", LOOKBACK_DAYS_DEFAULT))
    dep_date = _parse_date(deposit.get("deposit_date", ""))
    since_date = dep_date - timedelta(days=lookback)

    tier_override = None
    if payor_profile:
        override = (payor_profile.get("email_tier_override") or "global").lower()
        if override != "global":
            tier_override = override

    tier_order = _get_tier_order(tier_override)

    last_error = None
    for tier in tier_order:
        try:
            emails = _fetch_from_tier(tier, since_date, payor_profile)
            set_active_tier(tier)
            log.info("Email scan succeeded via tier: %s (%d emails)", tier, len(emails))
            return emails
        except Exception as e:
            log.warning("Tier %s failed: %s. Trying next tier.", tier, e)
            last_error = e

    log.error("All email tiers failed. Last error: %s", last_error)
    set_active_tier("none")
    return []


def _fetch_from_tier(tier: str, since_date: datetime, payor_profile: Optional[dict]) -> list[dict]:
    """Fetch emails from a specific tier. Raises on any error."""
    if tier == TIER_GRAPH:
        client_id = get_config("graph_client_id", "")
        tenant_id = get_config("graph_tenant_id", "")
        if not client_id or not tenant_id:
            raise RuntimeError("Graph API not configured")
        from app.email.graph_api import GraphEmailClient
        client = GraphEmailClient(client_id=client_id, tenant_id=tenant_id)
        return client.fetch_emails(since_date, payor_profile)

    elif tier == TIER_IMAP:
        imap_email = get_config("imap_email", "")
        imap_enc   = get_config("imap_password_encrypted", "")
        if not imap_email or not imap_enc:
            raise RuntimeError("IMAP not configured")
        from app.crypto import decrypt
        from app.email.imap_client import ImapClient
        password = decrypt(imap_enc)
        client = ImapClient(imap_email, password)
        return client.fetch_emails(since_date, payor_profile)

    elif tier == TIER_FOLDER:
        # Folder watch inserts to email_cache directly; query it here
        return _fetch_from_email_cache(since_date, payor_profile)

    raise ValueError(f"Unknown tier: {tier}")


def _fetch_from_email_cache(since_date: datetime, payor_profile: Optional[dict]) -> list[dict]:
    """Return emails already in email_cache (populated by folder watch)."""
    since_str = since_date.isoformat()
    rows = get_db().execute(
        "SELECT * FROM email_cache WHERE fetched_at >= ? ORDER BY fetched_at DESC",
        (since_str,)
    ).fetchall()

    results = []
    for row in rows:
        d = dict(row)
        try:
            d["attachments"] = json.loads(d.get("attachments") or "[]")
        except Exception:
            d["attachments"] = []

        # Domain filter if payor profile specifies
        if payor_profile:
            prof_domain = (payor_profile.get("sender_domain") or "").lower()
            prof_email  = (payor_profile.get("sender_email") or "").lower()
            row_domain  = (d.get("sender_domain") or "").lower()
            row_sender  = (d.get("sender") or "").lower()
            if prof_email and row_sender and prof_email != row_sender:
                continue
            if prof_domain and row_domain and not row_domain.endswith(prof_domain):
                continue
        results.append(d)
    return results


def _get_tier_order(override: Optional[str]) -> list[str]:
    if override:
        return [override]
    order = get_config("email_tier_order", DEFAULT_TIER_ORDER)
    if isinstance(order, str):
        try:
            order = json.loads(order)
        except Exception:
            order = DEFAULT_TIER_ORDER
    return order


def _parse_date(date_str: str) -> datetime:
    """Parse a deposit date string into a datetime, defaulting to today."""
    if not date_str:
        return datetime.now(timezone.utc)
    from dateutil.parser import parse
    try:
        dt = parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def cache_emails(email_list: list[dict]):
    """Insert a list of email dicts into email_cache (de-duplicated by message_id)."""
    import html2text
    db = get_db()
    for em in email_list:
        body_text = em.get("body_text", "")
        body_html = em.get("body_html", "")
        if body_html and not body_text:
            h = html2text.HTML2Text()
            h.ignore_links = False
            body_text = h.handle(body_html)

        try:
            db.execute("""
                INSERT INTO email_cache
                    (message_id, subject, sender, sender_domain, received_date,
                     body_text, attachments, source_tier, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(message_id) DO UPDATE SET
                    body_text = excluded.body_text,
                    fetched_at = excluded.fetched_at
            """, (
                em.get("message_id", ""),
                em.get("subject", ""),
                em.get("sender", ""),
                em.get("sender_domain", ""),
                em.get("received_date", ""),
                body_text,
                json.dumps(em.get("attachments", [])),
                em.get("source_tier", ""),
                now_iso(),
            ))
        except Exception as e:
            log.warning("Failed to cache email %s: %s", em.get("message_id"), e)
    db.commit()
