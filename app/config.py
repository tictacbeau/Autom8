"""
Central configuration: all paths derived from the project root.
Nothing is written outside PROJECT_ROOT at any time.
"""
import os
from pathlib import Path

# Absolute path to the project root (two levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

DATA_DIR        = PROJECT_ROOT / "data"
DB_PATH         = DATA_DIR / "remittance.db"
SECRET_KEY_PATH = DATA_DIR / "secret.key"
TOKENS_DIR      = DATA_DIR / "tokens"
WATCH_DIR       = DATA_DIR / "watch"
REMITTANCES_DIR = DATA_DIR / "remittances"
ATTACHMENTS_DIR = DATA_DIR / "attachments"

FLASK_SECRET    = os.urandom(32)   # ephemeral per-process; sessions are short-lived

# Microsoft 365 IMAP settings (fixed — no user editable)
IMAP_HOST = "outlook.office365.com"
IMAP_PORT = 993

# Matching thresholds
FUZZY_THRESHOLD      = 80    # minimum fuzz.ratio score for payor name match
AMOUNT_FUZZY_DELTA   = 1.00  # max $ difference allowed in fuzzy-amount tier
LOOKBACK_DAYS_DEFAULT = 7

# Email scan tier names
TIER_GRAPH  = "graph"
TIER_IMAP   = "imap"
TIER_FOLDER = "folder"

DEFAULT_TIER_ORDER = [TIER_GRAPH, TIER_IMAP, TIER_FOLDER]


def ensure_data_dirs():
    """Create all runtime data directories if they don't exist."""
    for d in (DATA_DIR, TOKENS_DIR, WATCH_DIR, REMITTANCES_DIR, ATTACHMENTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
