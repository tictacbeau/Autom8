"""Queue routes — pending, review, and manual queues."""
import json
from flask import Blueprint, jsonify, redirect, render_template, request, url_for, flash
from app.database import get_db, now_iso, get_pending_queue

queue_bp = Blueprint("queue", __name__)


# ---------------------------------------------------------------------------
# Pending queue
# ---------------------------------------------------------------------------

@queue_bp.route("/pending")
def pending():
    rows = get_pending_queue()
    return render_template("queue.html", tab="pending", items=rows)


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

@queue_bp.route("/review")
def review():
    db = get_db()
    rows = db.execute("""
        SELECT m.*, d.payor_name, d.amount, d.deposit_date, d.reference_number,
               ec.subject, ec.sender, ec.received_date, ec.source_tier
        FROM matches m
        JOIN deposits d ON d.id=m.deposit_id
        LEFT JOIN email_cache ec ON ec.id=m.email_cache_id
        WHERE m.status='pending_review'
        ORDER BY d.amount DESC
    """).fetchall()
    return render_template("queue.html", tab="review", items=rows)


# ---------------------------------------------------------------------------
# Manual queue
# ---------------------------------------------------------------------------

@queue_bp.route("/manual")
def manual():
    db = get_db()
    rows = db.execute("""
        SELECT d.*, p.name AS profile_name, p.notes AS profile_notes
        FROM deposits d
        JOIN payor_profiles p ON p.name=d.payor_name
        WHERE d.status='manual' AND p.manual_only=1
        ORDER BY d.amount DESC
    """).fetchall()
    return render_template("queue.html", tab="manual", items=rows)


# ---------------------------------------------------------------------------
# Confirm a review-queue match
# ---------------------------------------------------------------------------

@queue_bp.route("/review/<int:match_id>/confirm", methods=["POST"])
def confirm_match(match_id: int):
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if not match:
        return jsonify({"error": "Match not found"}), 404

    db.execute(
        "UPDATE matches SET status='confirmed', confirmed_at=? WHERE id=?",
        (now_iso(), match_id)
    )
    db.execute(
        "UPDATE deposits SET status='matched' WHERE id=?",
        (match["deposit_id"],)
    )
    # Remove from pending queue if present
    db.execute("DELETE FROM pending_queue WHERE deposit_id=?", (match["deposit_id"],))
    db.commit()

    if request.is_json:
        return jsonify({"ok": True})
    flash("Match confirmed.", "success")
    return redirect(url_for("queue.review"))


# ---------------------------------------------------------------------------
# Reject a review-queue match
# ---------------------------------------------------------------------------

@queue_bp.route("/review/<int:match_id>/reject", methods=["POST"])
def reject_match(match_id: int):
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if not match:
        return jsonify({"error": "Match not found"}), 404

    db.execute("UPDATE matches SET status='rejected' WHERE id=?", (match_id,))
    # Put deposit back in pending queue
    dep_id = match["deposit_id"]
    db.execute("UPDATE deposits SET status='pending' WHERE id=?", (dep_id,))
    ts = now_iso()
    db.execute("""
        INSERT INTO pending_queue(deposit_id, first_seen, last_scanned, scan_count)
        VALUES(?,?,?,1)
        ON CONFLICT(deposit_id) DO UPDATE SET last_scanned=excluded.last_scanned, scan_count=scan_count+1
    """, (dep_id, ts, ts))
    db.commit()

    if request.is_json:
        return jsonify({"ok": True})
    flash("Match rejected — deposit returned to pending queue.", "info")
    return redirect(url_for("queue.review"))


# ---------------------------------------------------------------------------
# Mark manual item complete
# ---------------------------------------------------------------------------

@queue_bp.route("/manual/<int:deposit_id>/complete", methods=["POST"])
def complete_manual(deposit_id: int):
    db = get_db()
    db.execute("UPDATE deposits SET status='matched' WHERE id=?", (deposit_id,))
    db.commit()

    if request.is_json:
        return jsonify({"ok": True})
    flash("Manual item marked complete.", "success")
    return redirect(url_for("queue.manual"))
