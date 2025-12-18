from flask import render_template, request, redirect, url_for, session
from . import auth_bp
from ..sqlite_db import query_db, execute_db

def normalize_phone(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = normalize_phone(request.form.get("phone"))
        name = (request.form.get("name") or "").strip() or None

        if not phone:
            return render_template("auth/login.html", error="Phone is required")

        user = query_db(
            "SELECT id FROM users WHERE phone_number = ?",
            (phone,),
            one=True,
        )

        if user is None:
            user_id = execute_db(
                "INSERT INTO users (phone_number, name) VALUES (?, ?)",
                (phone, name),
            )
        else:
            user_id = user["id"]

        session["user_id"] = user_id
        return redirect(url_for("appointments.list_appointments"))

    return render_template("auth/login.html", error=None)

@auth_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("auth.login"))
