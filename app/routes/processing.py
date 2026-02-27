"""
Processing routes — CSV upload, batch run, and status polling.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, redirect, render_template, request, url_for, flash

from app.database import (
    get_db, now_iso, get_all_payors, add_to_pending_queue,
    remove_from_pending_queue, get_config,
)

log = logging.getLogger(__name__)
processing_bp = Blueprint("processing", __name__)

# In-memory job progress store (keyed by job_id)
_jobs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# CSV Upload
# ---------------------------------------------------------------------------

@processing_bp.route("/upload-csv", methods=["POST"])
def upload_csv():
    if "csv_file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("dashboard.index"))

    f = request.files["csv_file"]
    if not f.filename:
        flash("No file selected.", "error")
        return redirect(url_for("dashboard.index"))

    if not f.filename.lower().endswith(".csv"):
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("dashboard.index"))

    try:
        from app.processing.csv_parser import parse_csv_file
        file_bytes = f.read()
        deposits, column_map = parse_csv_file(file_bytes)
    except ValueError as e:
        flash(f"CSV error: {e}", "error")
        return redirect(url_for("dashboard.index"))
    except Exception as e:
        log.exception("CSV upload error")
        flash(f"Could not parse CSV: {e}", "error")
        return redirect(url_for("dashboard.index"))

    if not deposits:
        flash("No deposit rows found in the CSV.", "warning")
        return redirect(url_for("dashboard.index"))

    # Store in session for confirmation step, or immediately start batch run
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db = get_db()
    cur = db.execute("""
        INSERT INTO batch_runs (run_date, csv_filename, total_deposits, status, created_at)
        VALUES (?,?,?,?,?)
    """, (today, f.filename, len(deposits), "running", now_iso()))
    batch_id = cur.lastrowid

    for dep in deposits:
        db.execute("""
            INSERT INTO deposits (batch_run_id, payor_name, amount, deposit_date, reference_number, raw_row, status, created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            batch_id,
            dep["payor_name"],
            dep["amount"],
            dep["deposit_date"],
            dep["reference_number"],
            json.dumps(dep["raw_row"]),
            "pending",
            now_iso(),
        ))
    db.commit()

    flash(f"Loaded {len(deposits)} deposits from {f.filename}. Ready to run batch.", "success")
    return redirect(url_for("processing.run_batch_ui", batch_id=batch_id))


# ---------------------------------------------------------------------------
# Batch run UI
# ---------------------------------------------------------------------------

@processing_bp.route("/batch/<int:batch_id>")
def run_batch_ui(batch_id: int):
    db = get_db()
    batch = db.execute("SELECT * FROM batch_runs WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        flash("Batch not found.", "error")
        return redirect(url_for("dashboard.index"))
    deposits = db.execute("SELECT * FROM deposits WHERE batch_run_id=? ORDER BY amount DESC", (batch_id,)).fetchall()
    return render_template("batch_run.html", batch=batch, deposits=deposits)


# ---------------------------------------------------------------------------
# Start batch job (AJAX)
# ---------------------------------------------------------------------------

@processing_bp.route("/run-batch", methods=["POST"])
def run_batch():
    data = request.get_json(silent=True) or {}
    batch_id = data.get("batch_id") or request.form.get("batch_id")
    if not batch_id:
        return jsonify({"error": "batch_id required"}), 400

    batch_id = int(batch_id)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 0, "message": "Starting..."}

    t = threading.Thread(
        target=_run_batch_worker,
        args=(batch_id, job_id),
        daemon=True,
        name=f"BatchWorker-{batch_id}",
    )
    t.start()

    return jsonify({"job_id": job_id})


# ---------------------------------------------------------------------------
# Status polling
# ---------------------------------------------------------------------------

@processing_bp.route("/status/<job_id>")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# ---------------------------------------------------------------------------
# Batch worker (runs in background thread)
# ---------------------------------------------------------------------------

def _run_batch_worker(batch_id: int, job_id: str):
    """
    Main batch processing logic.
    Imports are done inside the function to get fresh DB connections.
    """
    import sqlite3
    from app.config import DB_PATH
    from app.processing.matcher import match_deposit, identify_payor
    from app.email.email_manager import scan_emails_for_deposit, cache_emails, get_active_tier
    from app.output.pdf_generator import save_matched_pdf
    from app.config import REMITTANCES_DIR

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    def upd(msg: str, prog: int = None, total: int = None):
        job = _jobs[job_id]
        job["message"] = msg
        if prog is not None:
            job["progress"] = prog
        if total is not None:
            job["total"] = total

    try:
        # Fetch pending deposits for this batch + any in the carry-forward queue
        deposits = conn.execute("""
            SELECT d.* FROM deposits d
            WHERE d.batch_run_id=? AND d.status='pending'
            ORDER BY d.amount DESC
        """, (batch_id,)).fetchall()

        pending_queue = conn.execute("""
            SELECT d.* FROM deposits d
            JOIN pending_queue pq ON pq.deposit_id=d.id
            WHERE d.status='pending'
            ORDER BY d.amount DESC
        """).fetchall()

        all_deposits = list(deposits) + [d for d in pending_queue if d["batch_run_id"] != batch_id]
        all_profiles = conn.execute("SELECT * FROM payor_profiles").fetchall()

        total = len(all_deposits)
        upd("Scanning emails...", 0, total)

        matched = 0
        review_count = 0
        manual_count = 0

        output_folder = str(REMITTANCES_DIR)

        for i, deposit in enumerate(all_deposits):
            dep_dict = dict(deposit)
            upd(f"Processing {dep_dict['payor_name']} (${dep_dict['amount']:,.2f})", i, total)

            # Identify payor profile
            profile = identify_payor(dep_dict["payor_name"], [dict(p) for p in all_profiles])
            profile_dict = dict(profile) if profile else None

            # Manual-only payors → manual queue, skip matching
            if profile_dict and profile_dict.get("manual_only"):
                conn.execute(
                    "UPDATE deposits SET status='manual' WHERE id=?", (dep_dict["id"],)
                )
                conn.commit()
                manual_count += 1
                continue

            # Scan emails for this deposit
            try:
                emails = scan_emails_for_deposit(dep_dict, profile_dict)
                cache_emails(emails)
            except Exception as e:
                log.warning("Email scan failed for deposit %s: %s", dep_dict["id"], e)
                emails = []

            # Also check email_cache (folder watch results)
            from datetime import timedelta
            from app.email.email_manager import _fetch_from_email_cache, _parse_date
            try:
                lookback = int(get_config("lookback_days") or 7)
                dep_date = _parse_date(dep_dict.get("deposit_date", ""))
                since = dep_date - timedelta(days=lookback)
                cached_emails = _fetch_from_email_cache(since, profile_dict)
                all_emails = emails + [e for e in cached_emails if e["message_id"] not in {em["message_id"] for em in emails}]
            except Exception:
                all_emails = emails

            # Run matcher
            results = match_deposit(dep_dict, all_emails, profile_dict)

            if not results:
                # No match — add to pending queue
                _add_to_pending(conn, dep_dict["id"])
                continue

            if len(results) > 1 and results[0].tier == results[1].tier:
                # Multiple equally-confident matches → manual review
                for res in results[:3]:
                    _insert_match(conn, dep_dict["id"], res, "pending_review")
                conn.execute("UPDATE deposits SET status='review' WHERE id=?", (dep_dict["id"],))
                conn.commit()
                review_count += 1
                continue

            best = results[0]

            # Save PDF
            pdf_path = ""
            try:
                email_dict = dict(best.email)
                _add_body_text_from_cache(conn, email_dict)
                pdf_path = save_matched_pdf(email_dict, dep_dict, output_folder, profile_dict)
            except Exception as e:
                log.warning("PDF generation failed: %s", e)

            status = "matched" if best.auto_finalize else "review"
            match_status = "auto_finalized" if best.auto_finalize else "pending_review"

            _insert_match(conn, dep_dict["id"], best, match_status, pdf_path)
            conn.execute("UPDATE deposits SET status=? WHERE id=?", (status, dep_dict["id"]))
            conn.commit()

            if best.auto_finalize:
                # Remove from pending queue if it was there
                _remove_from_pending(conn, dep_dict["id"])
                matched += 1
            else:
                review_count += 1

        # Update batch summary
        pending_final = total - matched - review_count - manual_count
        active_tier = get_active_tier()
        conn.execute("""
            UPDATE batch_runs SET status='complete', matched=?, review=?, manual=?, pending=?, active_tier=?
            WHERE id=?
        """, (matched, review_count, manual_count, max(0, pending_final), active_tier, batch_id))
        conn.commit()

        upd(f"Done. {matched} matched, {review_count} for review, {pending_final} pending.", total, total)
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["batch_id"] = batch_id

    except Exception as e:
        log.exception("Batch worker error")
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["message"] = str(e)
        conn.execute("UPDATE batch_runs SET status='error' WHERE id=?", (batch_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_match(conn, deposit_id: int, result, status: str, pdf_path: str = ""):
    from app.database import now_iso
    conn.execute("""
        INSERT INTO matches
            (deposit_id, email_cache_id, confidence_tier, confidence_label,
             match_details, output_pdf_path, extraction_method, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        deposit_id,
        result.email.get("id"),
        result.tier,
        result.confidence_label,
        json.dumps(result.details),
        pdf_path,
        "",
        status,
        now_iso(),
    ))
    conn.commit()


def _add_to_pending(conn, deposit_id: int):
    from app.database import now_iso
    ts = now_iso()
    conn.execute("""
        INSERT INTO pending_queue (deposit_id, first_seen, last_scanned, scan_count)
        VALUES (?,?,?,1)
        ON CONFLICT(deposit_id) DO UPDATE SET last_scanned=excluded.last_scanned, scan_count=scan_count+1
    """, (deposit_id, ts, ts))
    conn.commit()


def _remove_from_pending(conn, deposit_id: int):
    conn.execute("DELETE FROM pending_queue WHERE deposit_id=?", (deposit_id,))
    conn.commit()


def _add_body_text_from_cache(conn, email_dict: dict):
    """Enrich email_dict with body_text from email_cache if not already present."""
    if email_dict.get("body_text"):
        return
    mid = email_dict.get("message_id")
    if not mid:
        return
    row = conn.execute("SELECT body_text FROM email_cache WHERE message_id=?", (mid,)).fetchone()
    if row:
        email_dict["body_text"] = row["body_text"] or ""
