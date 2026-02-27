"""Dashboard route."""
from flask import Blueprint, render_template
from app.database import get_db, get_config, get_pending_queue
from app.email.email_manager import get_active_tier

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@dashboard_bp.route("")
def index():
    db = get_db()

    # Latest batch run
    batch = db.execute(
        "SELECT * FROM batch_runs ORDER BY created_at DESC LIMIT 1"
    ).fetchone()

    # Stats
    pending_count = db.execute("SELECT COUNT(*) FROM pending_queue").fetchone()[0]
    review_count  = db.execute("SELECT COUNT(*) FROM matches WHERE status='pending_review'").fetchone()[0]
    manual_count  = db.execute(
        "SELECT COUNT(*) FROM deposits WHERE status='manual'"
    ).fetchone()[0]

    # Today's match rate
    match_rate = 0
    if batch and batch["total_deposits"] and batch["total_deposits"] > 0:
        match_rate = round(batch["matched"] / batch["total_deposits"] * 100)

    # Pending queue with aging
    pending_items = get_pending_queue()[:10]  # top 10 for dashboard

    # Recent processing log
    recent_log = db.execute(
        "SELECT * FROM processing_log ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    # Recent batches
    recent_batches = db.execute(
        "SELECT * FROM batch_runs ORDER BY created_at DESC LIMIT 5"
    ).fetchall()

    active_tier = get_active_tier()

    return render_template(
        "dashboard.html",
        batch=batch,
        pending_count=pending_count,
        review_count=review_count,
        manual_count=manual_count,
        match_rate=match_rate,
        pending_items=pending_items,
        recent_log=recent_log,
        recent_batches=recent_batches,
        active_tier=active_tier,
    )
