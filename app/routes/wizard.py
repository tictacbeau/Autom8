"""
Setup wizard routes — 7 steps.

State is stored in the config table (wizard_current_step, wizard_complete).
Each step can be skipped and returned to later from Settings.
"""
import json
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, session

from app.database import get_config, set_config, create_payor, get_all_payors
from app.config import WATCH_DIR, DEFAULT_TIER_ORDER

wizard_bp = Blueprint("wizard", __name__)

TOTAL_STEPS = 7


def _save_step(n: int):
    """Record progress without marking complete."""
    current = get_config("wizard_current_step", 1)
    if int(n) > int(current):
        set_config("wizard_current_step", int(n))


# ---------------------------------------------------------------------------
# GET /wizard/step/<n>  — render wizard step
# ---------------------------------------------------------------------------
@wizard_bp.route("/step/<int:n>", methods=["GET"])
def step(n: int):
    if n < 1 or n > TOTAL_STEPS:
        return redirect(url_for("wizard.step", n=1))

    ctx = {
        "step": n,
        "total": TOTAL_STEPS,
        "watch_dir": str(WATCH_DIR),
        "tier_order": get_config("email_tier_order", DEFAULT_TIER_ORDER),
        "graph_client_id": get_config("graph_client_id", ""),
        "graph_tenant_id": get_config("graph_tenant_id", ""),
        "imap_email": get_config("imap_email", ""),
        "graph_active": bool(get_config("graph_client_id")),
        "imap_active": bool(get_config("imap_email")),
        "folder_active": get_config("folder_tier_active", True),
        "wizard_complete": get_config("wizard_complete") == "1",
    }

    templates = {
        1: "wizard/step1_welcome.html",
        2: "wizard/step2_graph.html",
        3: "wizard/step3_imap.html",
        4: "wizard/step4_folder.html",
        5: "wizard/step5_priority.html",
        6: "wizard/step6_payor.html",
        7: "wizard/step7_ready.html",
    }
    return render_template(templates[n], **ctx)


# ---------------------------------------------------------------------------
# POST /wizard/step/<n>  — save step and advance
# ---------------------------------------------------------------------------
@wizard_bp.route("/step/<int:n>", methods=["POST"])
def step_post(n: int):
    action = request.form.get("action", "next")

    if n == 1:
        _save_step(1)

    elif n == 2:
        client_id = request.form.get("client_id", "").strip()
        tenant_id = request.form.get("tenant_id", "").strip()
        if client_id:
            set_config("graph_client_id", client_id)
        if tenant_id:
            set_config("graph_tenant_id", tenant_id)
        _save_step(2)

    elif n == 3:
        imap_email = request.form.get("imap_email", "").strip()
        imap_password = request.form.get("imap_password", "").strip()
        if imap_email:
            set_config("imap_email", imap_email)
        if imap_password:
            from app.crypto import encrypt
            set_config("imap_password_encrypted", encrypt(imap_password))
        _save_step(3)

    elif n == 4:
        # Folder watch is always active — just confirm
        set_config("folder_tier_active", True)
        _save_step(4)

    elif n == 5:
        raw_order = request.form.get("tier_order", "")
        if raw_order:
            try:
                order = json.loads(raw_order)
                set_config("email_tier_order", order)
            except (json.JSONDecodeError, ValueError):
                pass
        _save_step(5)

    elif n == 6:
        # Create first payor profile if data provided
        name = request.form.get("name", "").strip()
        if name:
            data = {
                "name": name,
                "sender_email": request.form.get("sender_email", "").strip(),
                "sender_domain": request.form.get("sender_domain", "").strip(),
                "subject_keywords": [k.strip() for k in request.form.get("subject_keywords", "").split(",") if k.strip()],
                "save_mode": request.form.get("save_mode", "both"),
                "custom_ref_labels": [l.strip() for l in request.form.get("custom_ref_labels", "").split(",") if l.strip()],
                "manual_only": int(request.form.get("manual_only", 0)),
                "email_tier_override": request.form.get("email_tier_override", "global"),
                "notes": request.form.get("notes", "").strip(),
            }
            create_payor(data)
        _save_step(6)
        # Allow "add another" option
        if action == "add_another":
            return redirect(url_for("wizard.step", n=6))

    elif n == 7:
        set_config("wizard_complete", "1")
        return redirect(url_for("dashboard.index"))

    # Skip or next
    if action == "skip":
        next_step = n + 1
    else:
        next_step = n + 1

    if next_step > TOTAL_STEPS:
        set_config("wizard_complete", "1")
        return redirect(url_for("dashboard.index"))

    return redirect(url_for("wizard.step", n=next_step))


# ---------------------------------------------------------------------------
# POST /wizard/test-graph  — test Graph API connection (AJAX)
# ---------------------------------------------------------------------------
@wizard_bp.route("/test-graph", methods=["POST"])
def test_graph():
    client_id = request.json.get("client_id", "").strip()
    tenant_id = request.json.get("tenant_id", "").strip()

    if not client_id or not tenant_id:
        return jsonify({"ok": False, "message": "Client ID and Tenant ID are required."})

    try:
        from app.email.graph_api import GraphEmailClient
        client = GraphEmailClient(client_id=client_id, tenant_id=tenant_id)
        ok, msg = client.test_connection()
        return jsonify({"ok": ok, "message": msg})
    except Exception as e:
        return jsonify({"ok": False, "message": f"Error: {str(e)}"})


# ---------------------------------------------------------------------------
# POST /wizard/test-imap  — test IMAP connection (AJAX)
# ---------------------------------------------------------------------------
@wizard_bp.route("/test-imap", methods=["POST"])
def test_imap():
    email_addr = request.json.get("email", "").strip()
    password   = request.json.get("password", "").strip()

    if not email_addr or not password:
        return jsonify({"ok": False, "error_type": None, "message": "Email and password are required."})

    from app.email.imap_client import ImapClient
    result = ImapClient.test_connection(email_addr, password)
    return jsonify(result)


# ---------------------------------------------------------------------------
# GET /wizard/  — redirect to current step
# ---------------------------------------------------------------------------
@wizard_bp.route("/", methods=["GET"])
@wizard_bp.route("", methods=["GET"])
def root():
    current = get_config("wizard_current_step", 1)
    return redirect(url_for("wizard.step", n=int(current)))
