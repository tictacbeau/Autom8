"""Settings routes."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from app.database import get_config, set_config

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/")
def index():
    ctx = {
        "graph_client_id":   get_config("graph_client_id", ""),
        "graph_tenant_id":   get_config("graph_tenant_id", ""),
        "imap_email":        get_config("imap_email", ""),
        "imap_configured":   bool(get_config("imap_password_encrypted")),
        "tier_order":        get_config("email_tier_order", ["graph", "imap", "folder"]),
        "lookback_days":     get_config("lookback_days", 7),
        "output_folder":     get_config("output_folder", "data/remittances"),
        "wizard_complete":   get_config("wizard_complete") == "1",
    }
    return render_template("settings.html", **ctx)


@settings_bp.route("/save", methods=["POST"])
def save_settings():
    lookback = request.form.get("lookback_days", "7").strip()
    try:
        lookback_int = max(1, min(30, int(lookback)))
        set_config("lookback_days", lookback_int)
    except ValueError:
        flash("Lookback days must be a number between 1 and 30.", "error")
        return redirect(url_for("settings.index"))

    flash("Settings saved.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/restart-wizard", methods=["POST"])
def restart_wizard():
    set_config("wizard_complete", "0")
    set_config("wizard_current_step", 1)
    flash("Wizard reset. Complete setup to continue.", "info")
    return redirect(url_for("wizard.step", n=1))
