"""
5-Tier matching engine.

For each deposit, attempts to match against a list of email dicts in order:
  Tier 1 — Exact: payor + amount + reference number
  Tier 2 — Strong: payor + amount
  Tier 3 — Domain + Amount: sender domain matches payor profile + amount
  Tier 4 — Fuzzy + Amount: fuzzy payor name match + amount within ±$1
  Tier 5 — Reference Only: unique reference number in email matches deposit

Tiers 1–2 are auto-finalized.
Tiers 3–5 go to the review queue.
Multiple matches for the same deposit → flagged for manual review.

All matching is independent of date (date is never a disqualifier;
it may be used only as a tiebreaker between otherwise-equal matches).
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rapidfuzz import fuzz

from app.config import FUZZY_THRESHOLD, AMOUNT_FUZZY_DELTA
from app.processing.ref_extractor import extract_ref_numbers, extract_amounts_from_text
from app.processing.text_extractor import extract_text_from_email_dict

log = logging.getLogger(__name__)

TIER_LABELS = {
    1: "Exact (payor + amount + reference)",
    2: "Strong (payor + amount)",
    3: "Domain + amount",
    4: "Fuzzy name + amount",
    5: "Reference number only",
}

AUTO_FINALIZE_TIERS = {1, 2}


@dataclass
class MatchResult:
    tier: int
    confidence_label: str
    email: dict
    score: float
    details: dict = field(default_factory=dict)
    auto_finalize: bool = False

    def __post_init__(self):
        self.auto_finalize = self.tier in AUTO_FINALIZE_TIERS


def match_deposit(
    deposit: dict,
    emails: list[dict],
    payor_profile: Optional[dict],
    all_payor_profiles: Optional[list[dict]] = None,
) -> list[MatchResult]:
    """
    Try all 5 tiers against a deposit+email list.
    Returns ALL matches found (caller checks for multiple matches).
    Empty list → unmatched.
    """
    if not emails:
        return []

    dep_amount = float(deposit.get("amount") or 0)
    dep_ref    = (deposit.get("reference_number") or "").strip().upper()
    dep_payor  = (deposit.get("payor_name") or "").strip()

    custom_labels = []
    payor_name_canonical = dep_payor
    payor_domain = ""
    if payor_profile:
        raw_labels = payor_profile.get("custom_ref_labels") or []
        if isinstance(raw_labels, str):
            try:
                raw_labels = json.loads(raw_labels)
            except Exception:
                raw_labels = []
        custom_labels = raw_labels
        payor_name_canonical = payor_profile.get("name") or dep_payor
        payor_domain = (payor_profile.get("sender_domain") or "").lower()

    all_matches: list[MatchResult] = []

    for email_dict in emails:
        full_text = extract_text_from_email_dict(email_dict)
        subject   = (email_dict.get("subject") or "").lower()
        combined  = (full_text + "\n" + subject).strip()

        email_refs   = {v.upper() for _, v in extract_ref_numbers(combined, custom_labels)}
        email_amounts = extract_amounts_from_text(combined)
        sender_domain = (email_dict.get("sender_domain") or "").lower()

        # ---- Tier 1 — Exact ----
        if dep_ref and dep_ref in email_refs:
            name_match = _payor_name_matches(dep_payor, payor_name_canonical, email_dict, payor_domain)
            amount_match = _amount_matches_exact(dep_amount, email_amounts)
            if name_match and amount_match:
                all_matches.append(MatchResult(
                    tier=1,
                    confidence_label=TIER_LABELS[1],
                    email=email_dict,
                    score=100.0,
                    details={"matched_ref": dep_ref, "matched_amount": dep_amount},
                ))
                continue  # best possible; no need to check lower tiers for this email

        # ---- Tier 2 — Strong: payor + amount ----
        name_match = _payor_name_matches(dep_payor, payor_name_canonical, email_dict, payor_domain)
        amount_match = _amount_matches_exact(dep_amount, email_amounts)
        if name_match and amount_match:
            all_matches.append(MatchResult(
                tier=2,
                confidence_label=TIER_LABELS[2],
                email=email_dict,
                score=90.0,
                details={"matched_amount": dep_amount},
            ))
            continue

        # ---- Tier 3 — Domain + amount ----
        if payor_domain and sender_domain and sender_domain.endswith(payor_domain):
            if _amount_matches_exact(dep_amount, email_amounts):
                all_matches.append(MatchResult(
                    tier=3,
                    confidence_label=TIER_LABELS[3],
                    email=email_dict,
                    score=70.0,
                    details={"matched_domain": sender_domain, "matched_amount": dep_amount},
                ))
                continue

        # ---- Tier 4 — Fuzzy name + amount (±$1) ----
        fuzzy_score = _fuzzy_name_score(dep_payor, payor_name_canonical, combined)
        if fuzzy_score >= FUZZY_THRESHOLD:
            if _amount_matches_fuzzy(dep_amount, email_amounts, AMOUNT_FUZZY_DELTA):
                closest_amount = _closest_amount(dep_amount, email_amounts)
                all_matches.append(MatchResult(
                    tier=4,
                    confidence_label=TIER_LABELS[4],
                    email=email_dict,
                    score=fuzzy_score,
                    details={"fuzzy_score": fuzzy_score, "matched_amount": closest_amount},
                ))
                continue

        # ---- Tier 5 — Reference number only ----
        if dep_ref and dep_ref in email_refs:
            all_matches.append(MatchResult(
                tier=5,
                confidence_label=TIER_LABELS[5],
                email=email_dict,
                score=60.0,
                details={"matched_ref": dep_ref},
            ))

    # Sort: lowest tier number (highest confidence) first; within same tier by score desc
    all_matches.sort(key=lambda m: (m.tier, -m.score))

    # Use date proximity only as a tiebreaker within same tier+score
    if len(all_matches) > 1:
        all_matches = _tiebreak_by_date(all_matches, deposit.get("deposit_date", ""))

    return all_matches


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _payor_name_matches(dep_payor: str, canonical: str, email_dict: dict, payor_domain: str) -> bool:
    """Check if this email is from the right payor (exact name match or sender domain)."""
    sender = (email_dict.get("sender") or "").lower()
    domain = (email_dict.get("sender_domain") or "").lower()

    # If domain is specified and matches, trust it
    if payor_domain and domain.endswith(payor_domain):
        return True

    # Try name match against email body/subject
    subject = (email_dict.get("subject") or "").lower()
    body    = (email_dict.get("body_text") or "").lower()
    search_text = subject + " " + body[:2000]

    if dep_payor and dep_payor.lower() in search_text:
        return True
    if canonical and canonical.lower() in search_text:
        return True

    return False


def _amount_matches_exact(target: float, amounts: list[float], tolerance: float = 0.01) -> bool:
    return any(abs(a - target) <= tolerance for a in amounts)


def _amount_matches_fuzzy(target: float, amounts: list[float], delta: float) -> bool:
    return any(abs(a - target) <= delta for a in amounts)


def _closest_amount(target: float, amounts: list[float]) -> Optional[float]:
    if not amounts:
        return None
    return min(amounts, key=lambda a: abs(a - target))


def _fuzzy_name_score(dep_payor: str, canonical: str, text: str) -> float:
    """Return best fuzzy match score between payor names and email text."""
    if not dep_payor and not canonical:
        return 0.0
    text_lower = text.lower()[:3000]  # limit search window for performance
    scores = []
    for name in {dep_payor, canonical}:
        if name:
            scores.append(fuzz.partial_ratio(name.lower(), text_lower))
    return max(scores) if scores else 0.0


def _tiebreak_by_date(matches: list[MatchResult], deposit_date_str: str) -> list[MatchResult]:
    """Sort matches of the same tier+score by date proximity to deposit_date."""
    if not deposit_date_str:
        return matches

    try:
        from dateutil.parser import parse
        dep_dt = parse(deposit_date_str)
    except Exception:
        return matches

    def _date_distance(m: MatchResult) -> float:
        email_date = m.email.get("received_date", "")
        if not email_date:
            return 9999.0
        try:
            from dateutil.parser import parse as dp
            ed = dp(email_date)
            return abs((ed - dep_dt).total_seconds())
        except Exception:
            return 9999.0

    return sorted(matches, key=lambda m: (m.tier, -m.score, _date_distance(m)))


# ---------------------------------------------------------------------------
# Identify payor from deposit row (pre-matching step)
# ---------------------------------------------------------------------------

def identify_payor(deposit_payor_name: str, all_profiles: list[dict]) -> Optional[dict]:
    """
    Fuzzy-match the deposit payor name against all profiles.
    Returns the best-matching profile, or None.
    """
    if not deposit_payor_name or not all_profiles:
        return None

    best_score = 0
    best_profile = None

    for profile in all_profiles:
        profile_name = profile.get("name") or ""
        score = fuzz.ratio(deposit_payor_name.lower(), profile_name.lower())
        if score > best_score:
            best_score = score
            best_profile = profile

    # Require at least 75% similarity
    if best_score >= 75:
        return best_profile
    return None
