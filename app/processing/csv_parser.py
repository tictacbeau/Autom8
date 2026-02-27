"""
CSV parser for deposit reports.

Auto-detects column names using synonym lists for:
  payor_name, amount, deposit_date, reference_number

Returns a list of normalised deposit dicts and the detected column mapping.
"""
import csv
import io
import logging
from typing import Optional

from dateutil.parser import parse as parse_date

log = logging.getLogger(__name__)

# Synonym lists for auto-detection (lowercase)
COLUMN_SYNONYMS = {
    "payor_name": [
        "payor", "payer", "payorname", "payer name", "payor name",
        "customer", "customer name", "company", "company name",
        "vendor", "vendor name", "client", "client name", "name",
        "remitter", "originator",
    ],
    "amount": [
        "amount", "deposit amount", "depositamount", "deposit", "total",
        "payment amount", "payment", "credit amount", "credit", "value",
        "transaction amount", "net amount", "gross amount",
    ],
    "deposit_date": [
        "date", "deposit date", "depositdate", "deposit_date",
        "received", "received date", "received_date", "posted",
        "posted date", "post date", "value date", "settlement date",
        "settlement", "transaction date", "entry date",
    ],
    "reference_number": [
        "reference", "reference number", "ref number", "ref no", "ref #",
        "reference #", "ref", "check", "check number", "check no",
        "trace", "trace number", "ach trace", "transaction id",
        "transaction number", "confirmation", "confirmation number",
        "payment reference", "payment id", "wire reference",
        "voucher", "voucher number", "invoice", "invoice number",
    ],
}


def parse_csv_file(file_content: bytes) -> tuple[list[dict], dict]:
    """
    Parse a CSV file from bytes.

    Returns:
        (deposits: list[dict], column_map: dict)
        column_map maps canonical names to detected column names.
        Missing optional columns will have None in the map.
    """
    # Try to detect encoding
    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = file_content.decode("latin-1")
        except Exception:
            text = file_content.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV appears to be empty or has no header row.")

    column_map = _detect_columns(list(reader.fieldnames))
    if not column_map.get("payor_name"):
        raise ValueError(
            f"Could not identify a payor name column in: {list(reader.fieldnames)}. "
            "Ensure the CSV has a column named 'Payor', 'Customer', 'Company', or similar."
        )
    if not column_map.get("amount"):
        raise ValueError(
            f"Could not identify an amount column in: {list(reader.fieldnames)}. "
            "Ensure the CSV has a column named 'Amount', 'Deposit', 'Payment', or similar."
        )

    deposits = []
    row_num = 1
    for row in reader:
        row_num += 1
        try:
            deposit = _normalise_row(row, column_map, row_num)
            if deposit:
                deposits.append(deposit)
        except Exception as e:
            log.warning("Row %d skipped: %s", row_num, e)

    return deposits, column_map


def _detect_columns(fieldnames: list[str]) -> dict:
    """Map canonical column names to actual CSV header names."""
    normalised = {f.strip().lower(): f for f in fieldnames}
    result = {}
    for canonical, synonyms in COLUMN_SYNONYMS.items():
        found = None
        for syn in synonyms:
            if syn in normalised:
                found = normalised[syn]
                break
        result[canonical] = found
    return result


def _normalise_row(row: dict, column_map: dict, row_num: int) -> Optional[dict]:
    """Convert a raw CSV row to a normalised deposit dict."""
    def get(canonical: str) -> str:
        col = column_map.get(canonical)
        if col and col in row:
            return (row[col] or "").strip()
        return ""

    payor_name = get("payor_name")
    amount_str = get("amount")
    date_str   = get("deposit_date")
    ref_str    = get("reference_number")

    if not payor_name:
        return None  # Skip blank rows

    # Parse amount
    amount_clean = amount_str.replace("$", "").replace(",", "").strip()
    try:
        amount = float(amount_clean) if amount_clean else 0.0
    except ValueError:
        log.warning("Row %d: could not parse amount '%s'", row_num, amount_str)
        amount = 0.0

    # Parse date
    parsed_date = ""
    if date_str:
        try:
            dt = parse_date(date_str, dayfirst=False)
            parsed_date = dt.strftime("%Y-%m-%d")
        except Exception:
            parsed_date = date_str  # store raw if parse fails

    return {
        "payor_name":       payor_name,
        "amount":           amount,
        "deposit_date":     parsed_date,
        "reference_number": ref_str,
        "raw_row":          dict(row),
    }
