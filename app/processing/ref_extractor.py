"""
Reference number extraction from remittance text.

Searches case-insensitively for 30+ standard synonym labels
plus any custom labels defined in a payor profile.
"""
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Standard synonym list — all common reference number labels
# ---------------------------------------------------------------------------
STANDARD_LABELS = [
    "Reference Number",
    "Reference No",
    "Ref Number",
    "Ref No",
    "Ref #",
    "Ref#",
    "Reference #",
    "Payment Reference",
    "Payment Ref",
    "Transaction ID",
    "Transaction #",
    "Transaction No",
    "Trace Number",
    "Trace No",
    "ACH Trace",
    "ACH Trace Number",
    "Wire Reference",
    "Wire Ref",
    "Confirmation Number",
    "Confirmation No",
    "Confirmation #",
    "Check Number",
    "Check No",
    "Check #",
    "Cheque Number",
    "Cheque No",
    "EFT Reference",
    "EFT Ref",
    "EFT #",
    "EFT Number",
    "Remittance ID",
    "Remittance Number",
    "Payment ID",
    "Payment Number",
    "Invoice Number",
    "Invoice No",
    "Invoice #",
    "Voucher Number",
    "Voucher No",
    "Voucher #",
    "Document Number",
    "Document No",
    "Document #",
    "Order Number",
    "Order No",
    "PO Number",
    "PO #",
    "Batch Number",
    "Batch #",
    "IMAD",
    "OMAD",
]


def _build_pattern(labels: list[str]) -> re.Pattern:
    """Compile a regex that matches any label followed by a reference value."""
    # Sort by length (longest first) to prefer more specific matches
    sorted_labels = sorted(labels, key=len, reverse=True)
    escaped = [re.escape(label) for label in sorted_labels]
    label_group = "|".join(escaped)
    # After the label: optional colon, space, hash, dash, then capture alphanumeric ref
    pattern = rf'(?:{label_group})\s*[:\-#]?\s*([A-Za-z0-9][A-Za-z0-9\-\.\/]{1,30})'
    return re.compile(pattern, re.IGNORECASE)


_DEFAULT_PATTERN = _build_pattern(STANDARD_LABELS)


def extract_ref_numbers(
    text: str,
    custom_labels: Optional[list[str]] = None,
) -> list[tuple[str, str]]:
    """
    Search text for reference numbers using all standard synonyms + custom labels.

    Returns a list of (label_found, ref_value) tuples, deduplicated by ref_value.
    """
    if not text:
        return []

    all_labels = STANDARD_LABELS.copy()
    if custom_labels:
        all_labels.extend(custom_labels)

    pattern = _build_pattern(all_labels) if custom_labels else _DEFAULT_PATTERN

    seen_values = set()
    results = []

    for match in pattern.finditer(text):
        ref_value = match.group(1).strip()
        # Filter out values that are obviously not reference numbers
        if len(ref_value) < 2:
            continue
        # Find which label matched (group 0 is full match, group 1 is the value)
        full_match = match.group(0)
        value_start = full_match.rfind(ref_value)
        label_part = full_match[:value_start].rstrip(": -#").strip()

        if ref_value.upper() not in seen_values:
            seen_values.add(ref_value.upper())
            results.append((label_part, ref_value))

    return results


def extract_amounts_from_text(text: str) -> list[float]:
    """
    Extract dollar amounts from text.
    Matches patterns like: $1,234.56  1234.56  1,234.56
    """
    if not text:
        return []

    # Match optional $ then digits with optional commas then optional decimal
    pattern = re.compile(r'\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)')
    amounts = []
    seen = set()

    for match in pattern.finditer(text):
        raw = match.group(1).replace(",", "")
        try:
            val = float(raw)
            if val > 0 and val not in seen:
                seen.add(val)
                amounts.append(val)
        except ValueError:
            pass

    return amounts
