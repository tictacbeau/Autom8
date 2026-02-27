"""Payor profile CRUD routes."""
import json
from flask import Blueprint, flash, redirect, render_template, request, url_for
from app.database import (
    get_all_payors, get_payor, create_payor, update_payor, delete_payor,
)

payors_bp = Blueprint("payors", __name__)


@payors_bp.route("/")
def list_payors():
    payors = get_all_payors()
    return render_template("payors/list.html", payors=payors)


@payors_bp.route("/new", methods=["GET"])
def new_payor():
    return render_template("payors/form.html", payor=None, action="Create")


@payors_bp.route("/new", methods=["POST"])
def create_payor_route():
    data = _extract_form()
    if not data.get("name"):
        flash("Payor name is required.", "error")
        return render_template("payors/form.html", payor=data, action="Create")
    try:
        payor_id = create_payor(data)
        flash(f"Payor '{data['name']}' created successfully.", "success")
        return redirect(url_for("payors.list_payors"))
    except Exception as e:
        if "UNIQUE" in str(e):
            flash(f"A payor named '{data['name']}' already exists.", "error")
        else:
            flash(f"Error creating payor: {e}", "error")
        return render_template("payors/form.html", payor=data, action="Create")


@payors_bp.route("/<int:payor_id>/edit", methods=["GET"])
def edit_payor(payor_id: int):
    payor = get_payor(payor_id)
    if not payor:
        flash("Payor not found.", "error")
        return redirect(url_for("payors.list_payors"))
    payor_dict = dict(payor)
    # Decode JSON fields for template
    for field in ("subject_keywords", "custom_ref_labels"):
        val = payor_dict.get(field, "[]")
        try:
            payor_dict[field] = ", ".join(json.loads(val)) if val else ""
        except Exception:
            payor_dict[field] = val or ""
    return render_template("payors/form.html", payor=payor_dict, action="Save")


@payors_bp.route("/<int:payor_id>/edit", methods=["POST"])
def update_payor_route(payor_id: int):
    payor = get_payor(payor_id)
    if not payor:
        flash("Payor not found.", "error")
        return redirect(url_for("payors.list_payors"))
    data = _extract_form()
    try:
        update_payor(payor_id, data)
        flash(f"Payor '{data['name']}' updated.", "success")
        return redirect(url_for("payors.list_payors"))
    except Exception as e:
        flash(f"Error updating payor: {e}", "error")
        return render_template("payors/form.html", payor=data, action="Save")


@payors_bp.route("/<int:payor_id>/delete", methods=["POST"])
def delete_payor_route(payor_id: int):
    payor = get_payor(payor_id)
    if payor:
        name = payor["name"]
        delete_payor(payor_id)
        flash(f"Payor '{name}' deleted.", "success")
    return redirect(url_for("payors.list_payors"))


def _extract_form() -> dict:
    return {
        "name":               request.form.get("name", "").strip(),
        "sender_email":       request.form.get("sender_email", "").strip(),
        "sender_domain":      request.form.get("sender_domain", "").strip(),
        "subject_keywords":   [k.strip() for k in request.form.get("subject_keywords", "").split(",") if k.strip()],
        "save_mode":          request.form.get("save_mode", "both"),
        "custom_ref_labels":  [l.strip() for l in request.form.get("custom_ref_labels", "").split(",") if l.strip()],
        "manual_only":        int(bool(request.form.get("manual_only"))),
        "email_tier_override": request.form.get("email_tier_override", "global"),
        "notes":              request.form.get("notes", "").strip(),
    }
