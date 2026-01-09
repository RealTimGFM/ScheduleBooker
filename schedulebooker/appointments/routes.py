from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta

from flask import abort, redirect, render_template, request, session, url_for

from . import appointments_bp
from ..sqlite_db import execute_db, query_db
from ..public.routes import SHOP_TIMEZONE, _validate_shop_hours_and_past


def _parse_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat((s or "").strip())
    except Exception:
        return None


def _parse_time(s: str | None) -> time | None:
    try:
        return time.fromisoformat((s or "").strip())
    except Exception:
        return None


def _generate_booking_code() -> str:
    for _ in range(5):
        code = secrets.token_urlsafe(8).replace("-", "").replace("_", "")
        exists = query_db(
            "SELECT 1 FROM appointments WHERE booking_code = ? LIMIT 1",
            (code,),
            one=True,
        )
        if not exists:
            return code
    return secrets.token_urlsafe(12).replace("-", "").replace("_", "")


def _require_user_id() -> int:
    uid = session.get("user_id")
    return int(uid) if uid else 0


@appointments_bp.route("/", methods=["GET"])
def list_appointments():
    user_id = _require_user_id()
    if not user_id:
        return redirect(url_for("auth.login"))

    appointments = query_db(
        """
        SELECT
            a.*,
            s.name AS service_name,
            b.name AS barber_name
        FROM appointments a
        LEFT JOIN services s ON s.id = a.service_id
        LEFT JOIN barbers b ON b.id = a.barber_id
        WHERE a.user_id = ?
        ORDER BY a.start_time DESC
        """,
        (user_id,),
    )
    return render_template("appointments/list.html", appointments=appointments)


# Backward-compatible alias (older templates/links may still call this)
@appointments_bp.route("", methods=["GET"], endpoint="my_appointments")
def my_appointments():
    return list_appointments()


@appointments_bp.route("/new", methods=["GET", "POST"])
def new_appointment():
    user_id = _require_user_id()
    if not user_id:
        return redirect(url_for("auth.login"))

    services = query_db("SELECT * FROM services WHERE is_active = 1 ORDER BY name ASC")
    barbers = query_db("SELECT * FROM barbers WHERE is_active = 1 ORDER BY name ASC")

    user = query_db("SELECT name FROM users WHERE id = ?", (user_id,), one=True)
    default_name = user["name"] if user and user["name"] is not None else ""
    default_phone = ""

    today_iso = datetime.now(SHOP_TIMEZONE).date().isoformat()

    if request.method == "GET":
        return render_template(
            "appointments/form.html",
            appt={"customer_name": default_name},
            services=services,
            barbers=barbers,
            open_time="11:00",
            close_time="19:00",
            today=today_iso,
        )

    service_id_raw = (request.form.get("service_id") or "").strip()
    barber_id_raw = (request.form.get("barber_id") or "").strip()  # optional
    day = _parse_date(request.form.get("date"))
    start_t = _parse_time(request.form.get("time"))
    notes = (request.form.get("notes") or "").strip()
    customer_name = (request.form.get("customer_name") or default_name).strip() or (
        default_name or "Customer"
    )

    appt_ctx: dict = {
        "customer_name": customer_name,
        "service_id": int(service_id_raw) if service_id_raw.isdigit() else None,
        "barber_id": int(barber_id_raw) if barber_id_raw.isdigit() else None,
        "notes": notes,
    }

    service_id = int(service_id_raw) if service_id_raw.isdigit() else 0
    service = query_db(
        "SELECT * FROM services WHERE id = ? AND is_active = 1",
        (service_id,),
        one=True,
    )
    if not service:
        return render_template(
            "appointments/form.html",
            appt=appt_ctx,
            services=services,
            barbers=barbers,
            open_time="11:00",
            close_time="19:00",
            today=today_iso,
            error="Please choose a service.",
        )

    if not day or not start_t:
        return render_template(
            "appointments/form.html",
            appt=appt_ctx,
            services=services,
            barbers=barbers,
            open_time="11:00",
            close_time="19:00",
            today=today_iso,
            error="Please choose a valid date and time.",
        )

    duration_min = int(service["duration_min"] or 30)
    start_dt = datetime.combine(day, start_t).replace(tzinfo=SHOP_TIMEZONE)
    end_dt = start_dt + timedelta(minutes=duration_min)
    end_t = end_dt.timetz().replace(tzinfo=None)

    # This enforces:
    # - not in the past
    # - not Monday closed
    # - start within OPEN..CLOSE
    # - end <= LAST_END_TIME
    err = _validate_shop_hours_and_past(day, start_t, end_t)
    if err:
        appt_ctx["start_time"] = start_dt.isoformat()
        return render_template(
            "appointments/form.html",
            appt=appt_ctx,
            services=services,
            barbers=barbers,
            open_time="11:00",
            close_time="19:00",
            today=today_iso,
            error=err,
        )

    barber_id = int(barber_id_raw) if barber_id_raw.isdigit() else None

    now = datetime.now(SHOP_TIMEZONE).isoformat()
    booking_code = _generate_booking_code()

    execute_db(
        """
        INSERT INTO appointments
          (customer_name, customer_phone, service_id, barber_id, user_id,
           start_time, end_time, notes, status, booking_code, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_name,
            default_phone,
            service_id,
            barber_id,
            user_id,
            start_dt.isoformat(),
            end_dt.isoformat(),
            notes,
            "booked",
            booking_code,
            now,
            now,
        ),
    )

    return redirect(url_for("appointments.list_appointments"))


@appointments_bp.route("/<int:appt_id>/edit", methods=["GET", "POST"])
def edit_appointment(appt_id: int):
    user_id = _require_user_id()
    if not user_id:
        return redirect(url_for("auth.login"))

    appt = query_db("SELECT * FROM appointments WHERE id = ?", (appt_id,), one=True)
    if not appt or int(appt["user_id"] or 0) != user_id:
        abort(404)

    services = query_db("SELECT * FROM services WHERE is_active = 1 ORDER BY name ASC")
    barbers = query_db("SELECT * FROM barbers WHERE is_active = 1 ORDER BY name ASC")

    if request.method == "GET":
        appt_ctx = dict(appt)
        return render_template(
            "appointments/form.html",
            appt=appt_ctx,
            services=services,
            barbers=barbers,
            open_time="11:00",
            close_time="19:00",
            today=datetime.now(SHOP_TIMEZONE).date().isoformat(),
        )

    notes = (request.form.get("notes") or "").strip()
    now = datetime.now(SHOP_TIMEZONE).isoformat()
    execute_db(
        "UPDATE appointments SET notes = ?, updated_at = ? WHERE id = ?",
        (notes, now, appt_id),
    )
    return redirect(url_for("appointments.list_appointments"))


@appointments_bp.route("/<int:appt_id>/delete", methods=["POST"])
def delete_appointment(appt_id: int):
    user_id = _require_user_id()
    if not user_id:
        return redirect(url_for("auth.login"))

    appt = query_db(
        "SELECT user_id FROM appointments WHERE id = ?",
        (appt_id,),
        one=True,
    )
    if not appt or int(appt["user_id"] or 0) != user_id:
        abort(404)

    now = datetime.now(SHOP_TIMEZONE).isoformat()
    execute_db(
        "UPDATE appointments SET status = 'cancelled', cancelled_at = ?, updated_at = ? WHERE id = ?",
        (now, now, appt_id),
    )
    return redirect(url_for("appointments.list_appointments"))
