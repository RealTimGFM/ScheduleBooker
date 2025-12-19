from __future__ import annotations

from flask import jsonify, redirect, render_template, request, session, url_for
from jinja2 import TemplateNotFound
from werkzeug.security import check_password_hash

from ..sqlite_db import query_db
from . import admin_bp


def render_or_json(template_name: str, **ctx):
    try:
        return render_template(template_name, **ctx)
    except TemplateNotFound:
        return jsonify({"template": template_name, "context": ctx})


def require_admin():
    return session.get("admin_user_id") is not None


@admin_bp.get("/login")
def login():
    return render_or_json("admin/login.html", error=None)


@admin_bp.post("/login")
def login_post():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    row = query_db(
        "SELECT id, password_hash FROM admin_users WHERE username = ?",
        (username,),
        one=True,
    )

    if not row or not check_password_hash(row["password_hash"], password):
        return render_or_json("admin/login.html", error="Invalid username/password")

    session["admin_user_id"] = row["id"]
    return redirect(url_for("admin.day"))


@admin_bp.get("/day")
def day():
    if not require_admin():
        return redirect(url_for("admin.login"))

    date_str = request.args.get("date")
    bookings = []  # Day 5 will load real bookings
    return render_or_json("admin/day.html", date=date_str, bookings=bookings, error=None)


@admin_bp.post("/book")
def create_booking():
    if not require_admin():
        return redirect(url_for("admin.login"))

    # Day 5 will create bookings with NO validations
    return redirect(url_for("admin.day"))
