from __future__ import annotations

import re

from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..sqlite_db import execute_db, query_db
from . import auth_bp

_PIN_RE = re.compile(r"^\d{6}$")


def normalize_phone(phone: str | None) -> str:
    """Keep only digits so we store phones consistently."""
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _get_user_by_phone(phone_number: str):
    return query_db("SELECT * FROM users WHERE phone_number = ?", (phone_number,), one=True)


@auth_bp.get("/login")
def login():
    return render_template("auth/login.html", error=None)


@auth_bp.post("/login")
def login_post():
    phone = normalize_phone(request.form.get("phone"))
    pin = (request.form.get("pin") or "").strip()

    if not phone:
        return render_template("auth/login.html", error="Phone is required")

    if not _PIN_RE.match(pin):
        return render_template("auth/login.html", error="PIN must be exactly 6 digits")

    row = _get_user_by_phone(phone)
    if not row:
        return render_template("auth/login.html", error="No account found. Please sign up first.")

    pw_hash = (row["password_hash"] or "").strip()
    if not pw_hash:
        return render_template(
            "auth/login.html", error="This account has no PIN yet. Please sign up."
        )

    if not check_password_hash(pw_hash, pin):
        return render_template("auth/login.html", error="Invalid phone or PIN")

    session["user_id"] = int(row["id"])
    return redirect(url_for("appointments.list_appointments"))


@auth_bp.get("/signup")
def signup():
    return render_template("auth/signup.html", error=None)


@auth_bp.post("/signup")
def signup_post():
    phone = normalize_phone(request.form.get("phone"))
    name = (request.form.get("name") or "").strip()
    pin = (request.form.get("pin") or "").strip()
    pin2 = (request.form.get("pin2") or "").strip()

    if not name:
        return render_template("auth/signup.html", error="Name is required")

    if not phone:
        return render_template("auth/signup.html", error="Phone is required")

    if not _PIN_RE.match(pin):
        return render_template("auth/signup.html", error="PIN must be exactly 6 digits")

    if pin != pin2:
        return render_template("auth/signup.html", error="PINs do not match")

    row = _get_user_by_phone(phone)
    pw_hash = generate_password_hash(pin)

    if row:
        # If the account already has a PIN, force login instead.
        existing_hash = (row["password_hash"] or "").strip()
        if existing_hash:
            return render_template(
                "auth/signup.html",
                error="That phone already has an account. Please sign in.",
            )

        # Backward-compat: “claim” existing account created previously (no PIN)
        execute_db(
            "UPDATE users SET name = ?, password_hash = ? WHERE id = ?",
            (name, pw_hash, int(row["id"])),
        )
        user_id = int(row["id"])
    else:
        user_id = int(
            execute_db(
                "INSERT INTO users (phone_number, name, password_hash) VALUES (?, ?, ?)",
                (phone, name, pw_hash),
            )
        )

    session["user_id"] = user_id
    return redirect(url_for("appointments.list_appointments"))


@auth_bp.get("/logout")
def logout():
    # Do NOT session.clear() because that can wipe admin session too.
    session.pop("user_id", None)
    return redirect(url_for("public.services"))
