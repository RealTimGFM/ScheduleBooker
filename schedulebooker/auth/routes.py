from __future__ import annotations

from flask import redirect, render_template, request, session, url_for

from ..sqlite_db import execute_db, query_db
from . import auth_bp


def normalize_phone(phone: str | None) -> str:
    """Keep only digits so we store phones consistently."""
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _get_or_create_user(phone_number: str, name: str | None) -> int:
    row = query_db(
        "SELECT id, name FROM users WHERE phone_number = ?",
        (phone_number,),
        one=True,
    )

    if row:
        user_id = int(row["id"])
        # If they provided a name and we don't have one yet, update it.
        if name and not (row["name"] or "").strip():
            execute_db("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
        return user_id

    user_id = execute_db(
        "INSERT INTO users (phone_number, name) VALUES (?, ?)",
        (phone_number, name),
    )
    return int(user_id)


@auth_bp.get("/login")
def login():
    return render_template("auth/login.html", error=None)


@auth_bp.post("/login")
def login_post():
    phone = normalize_phone(request.form.get("phone"))
    name = (request.form.get("name") or "").strip() or None

    if not phone:
        return render_template("auth/login.html", error="Phone is required")

    user_id = _get_or_create_user(phone, name)
    session["user_id"] = user_id

    # Keep original behavior: after login, go to the user's appointments page.
    return redirect(url_for("appointments.list_appointments"))


@auth_bp.get("/signup")
def signup():
    return render_template("auth/signup.html", error=None)


@auth_bp.post("/signup")
def signup_post():
    phone = normalize_phone(request.form.get("phone"))
    name = (request.form.get("name") or "").strip() or None

    if not phone:
        return render_template("auth/signup.html", error="Phone is required")

    user_id = _get_or_create_user(phone, name)
    session["user_id"] = user_id
    return redirect(url_for("appointments.list_appointments"))


@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("public.services"))
