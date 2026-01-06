from datetime import date, datetime, time

from flask import abort, flash, redirect, render_template, request, session, url_for

from ..public.routes import SHOP_TIMEZONE
from ..sqlite_db import execute_db, query_db
from . import appointments_bp


def _floor_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def _validate_not_past(date_str: str | None, time_str: str | None) -> str | None:
    """
    Customer-facing validation: reject bookings strictly earlier than "now"
    in shop timezone, compared at minute precision.
    """
    if not date_str or not time_str:
        return "Missing date/time."

    try:
        d = date.fromisoformat(date_str)
        t_raw = time.fromisoformat(time_str)
        t = time(t_raw.hour, t_raw.minute)  # ensure minute precision
    except Exception:
        return "Invalid date/time."

    requested = _floor_to_minute(datetime.combine(d, t, tzinfo=SHOP_TIMEZONE))
    now = _floor_to_minute(datetime.now(SHOP_TIMEZONE))

    if requested < now:
        return "Cannot book in the past."

    return None


@appointments_bp.route("/")
def list_appointments():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    # Claim guest bookings (user_id IS NULL) that match this user's phone
    user = query_db("SELECT phone_number FROM users WHERE id = ?", (user_id,), one=True)
    phone = None
    if user is not None:
        try:
            phone = user["phone_number"]
        except Exception:
            phone = None

    if phone:
        execute_db(
            """
            UPDATE appointments
            SET user_id = ?
            WHERE user_id IS NULL AND customer_phone = ?
            """,
            (user_id, phone),
        )

    appts = query_db(
        """
        SELECT a.*, s.name AS service_name
        FROM appointments a
        LEFT JOIN services s ON s.id = a.service_id
        WHERE a.user_id = ?
        ORDER BY a.start_time ASC
        """,
        (user_id,),
    )

    # Template expects "appointments"
    return render_template("appointments/list.html", appointments=appts, appts=appts)


@appointments_bp.route("/new", methods=["GET", "POST"])
def new_appointment():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    svc_rows = query_db("SELECT id, name FROM services ORDER BY name")
    services = [(r["id"], r["name"]) for r in svc_rows]

    today_min = datetime.now(SHOP_TIMEZONE).date().isoformat()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        service_id = request.form.get("service_id", type=int)
        date_str = request.form.get("date")
        time_str = request.form.get("time")
        notes = request.form.get("notes", "")

        if not customer_name or not service_id or not date_str or not time_str:
            return render_template(
                "appointments/form.html",
                appointment={},
                services=services,
                today_min=today_min,
                error="Missing required fields.",
            )

        past_err = _validate_not_past(date_str, time_str)
        if past_err:
            return render_template(
                "appointments/form.html",
                appointment={},
                services=services,
                today_min=today_min,
                error=past_err,
            )

        start_iso = f"{date_str}T{time_str}:00"
        now_iso = datetime.utcnow().isoformat(timespec="seconds")

        execute_db(
            """
            INSERT INTO appointments (user_id, customer_name, service_id, start_time, notes, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'booked', ?, ?)
            """,
            (user_id, customer_name, service_id, start_iso, notes, now_iso, now_iso),
        )

        flash("Appointment created.", "success")
        return redirect(url_for("appointments.list_appointments"))

    return render_template(
        "appointments/form.html",
        appointment={},
        services=services,
        today_min=today_min,
    )


@appointments_bp.route("/<int:appt_id>/edit", methods=["GET", "POST"])
def edit_appointment(appt_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    appt = query_db(
        "SELECT * FROM appointments WHERE id = ? AND user_id = ?",
        (appt_id, user_id),
        one=True,
    )
    if not appt:
        abort(404)

    svc_rows = query_db("SELECT id, name FROM services ORDER BY name")
    services = [(r["id"], r["name"]) for r in svc_rows]
    today_min = datetime.now(SHOP_TIMEZONE).date().isoformat()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        service_id = request.form.get("service_id", type=int)
        date_str = request.form.get("date")
        time_str = request.form.get("time")
        notes = request.form.get("notes", "")

        # Keep user input on validation errors
        form_appt = {
            "id": appt_id,
            "customer_name": customer_name,
            "service_id": service_id,
            "date": date_str or "",
            "time": time_str or "",
            "notes": notes,
        }

        if not customer_name or not service_id or not date_str or not time_str:
            return render_template(
                "appointments/form.html",
                appointment=form_appt,
                services=services,
                today_min=today_min,
                error="Missing required fields.",
            )

        past_err = _validate_not_past(date_str, time_str)
        if past_err:
            return render_template(
                "appointments/form.html",
                appointment=form_appt,
                services=services,
                today_min=today_min,
                error=past_err,
            )

        start_iso = f"{date_str}T{time_str}:00"
        now_iso = datetime.utcnow().isoformat(timespec="seconds")

        execute_db(
            """
            UPDATE appointments
            SET customer_name = ?, service_id = ?, start_time = ?, notes = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (customer_name, service_id, start_iso, notes, now_iso, appt_id, user_id),
        )
        flash("Appointment updated.", "success")
        return redirect(url_for("appointments.list_appointments"))

    # Pre-fill date/time fields
    appt_dict = dict(appt)
    try:
        dt = datetime.fromisoformat(appt_dict["start_time"])
        appt_dict["date"] = dt.date().isoformat()
        appt_dict["time"] = dt.strftime("%H:%M")
    except Exception:
        appt_dict["date"] = ""
        appt_dict["time"] = ""

    return render_template(
        "appointments/form.html",
        appointment=appt_dict,
        services=services,
        today_min=today_min,
    )


@appointments_bp.route("/<int:appt_id>/delete", methods=["POST"])
def delete_appointment(appt_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    execute_db(
        "DELETE FROM appointments WHERE id = ? AND user_id = ?",
        (appt_id, user_id),
    )
    return redirect(url_for("appointments.list_appointments"))
