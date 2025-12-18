from datetime import datetime

from flask import abort, redirect, render_template, request, session, url_for

from ..sqlite_db import execute_db, query_db
from . import appointments_bp


def require_login():
    return session.get("user_id")


def get_services():
    rows = query_db("SELECT id, name FROM services ORDER BY name")
    return [(r["id"], r["name"]) for r in rows]


@appointments_bp.route("/")
def list_appointments():
    user_id = require_login()
    if not user_id:
        return redirect(url_for("auth.login"))

    appts = query_db(
        "SELECT a.id, a.customer_name, a.start_time, a.notes, a.service_id, "
        "       s.name AS service_name "
        "FROM appointments a "
        "LEFT JOIN services s ON s.id = a.service_id "
        "WHERE a.user_id = ? "
        "ORDER BY a.start_time",
        (user_id,),
    )
    return render_template("appointments/list.html", appointments=appts, error=None)


@appointments_bp.route("/new", methods=["GET", "POST"])
def new_appointment():
    user_id = require_login()
    if not user_id:
        return redirect(url_for("auth.login"))

    services = get_services()

    if request.method == "POST":
        customer_name = (request.form.get("customer_name") or "").strip()
        date_str = request.form.get("date")
        time_str = request.form.get("time")
        service_id = request.form.get("service_id")
        notes = request.form.get("notes") or ""

        if not (customer_name and date_str and time_str):
            return render_template(
                "appointments/form.html",
                appointment=None,
                services=services,
                error="Name, date, and time are required.",
            )

        start_iso = f"{date_str}T{time_str}:00"
        now_iso = datetime.utcnow().isoformat()

        execute_db(
            "INSERT INTO appointments (user_id, customer_name, start_time, notes, service_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, customer_name, start_iso, notes, service_id, now_iso, now_iso),
        )
        return redirect(url_for("appointments.list_appointments"))

    return render_template(
        "appointments/form.html", appointment=None, services=services, error=None
    )


@appointments_bp.route("/<int:appointment_id>/edit", methods=["GET", "POST"])
def edit_appointment(appointment_id):
    user_id = require_login()
    if not user_id:
        return redirect(url_for("auth.login"))

    appt = query_db("SELECT * FROM appointments WHERE id = ?", (appointment_id,), one=True)
    if not appt:
        abort(404)
    if appt["user_id"] != user_id:
        abort(403)

    services = get_services()
    dt = datetime.fromisoformat(appt["start_time"])
    date_val = dt.date().isoformat()
    time_val = dt.time().strftime("%H:%M")

    if request.method == "POST":
        customer_name = (request.form.get("customer_name") or "").strip()
        date_str = request.form.get("date")
        time_str = request.form.get("time")
        service_id = request.form.get("service_id")
        notes = request.form.get("notes") or ""

        if not (customer_name and date_str and time_str):
            return render_template(
                "appointments/form.html",
                appointment=appt,
                services=services,
                date_val=date_str,
                time_val=time_str,
                error="Name, date, and time are required.",
            )

        start_iso = f"{date_str}T{time_str}:00"
        now_iso = datetime.utcnow().isoformat()

        execute_db(
            "UPDATE appointments SET customer_name=?, start_time=?, notes=?, service_id=?, updated_at=? WHERE id=?",
            (customer_name, start_iso, notes, service_id, now_iso, appointment_id),
        )
        return redirect(url_for("appointments.list_appointments"))

    return render_template(
        "appointments/form.html",
        appointment=appt,
        services=services,
        date_val=date_val,
        time_val=time_val,
        error=None,
    )
