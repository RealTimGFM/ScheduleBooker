# schedulebooker/appointments/routes.py

from datetime import date, datetime, time, timedelta

from flask import abort, flash, redirect, render_template, request, session, url_for

from ..public.routes import (
    MAX_BOOKINGS_PER_DAY_MESSAGE,
    SHOP_CAPACITY_PER_SLOT,
    SHOP_TIMEZONE,
    _iso,
    _load_bookings_for_day,
    _overlaps,
    _slot_segments_30min,
    _validate_shop_hours_and_past,
)
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


def _validate_customer_portal_booking(
    *,
    day: date,
    start_t: time,
    duration_min: int,
    user_id: int,
    booking_id: int | None = None,
):
    start_dt = datetime.combine(day, start_t)
    end_dt = start_dt + timedelta(minutes=duration_min)

    # Shop hours + Monday + end <= 18:30 + no past
    hours_error = _validate_shop_hours_and_past(day, start_t, end_dt.time())
    if hours_error:
        return None, None, hours_error

    existing = _load_bookings_for_day(day)

    # service duration lookup (for old rows missing end_time)
    svc_rows = query_db("SELECT id, duration_min FROM services")
    svc_duration = {r["id"]: r["duration_min"] for r in svc_rows}

    # User daily max (2)
    user_bookings_today = [
        b
        for b in existing
        if b.get("user_id") == user_id and (not booking_id or b["id"] != booking_id)
    ]
    if len(user_bookings_today) >= 2:
        return None, None, MAX_BOOKINGS_PER_DAY_MESSAGE

    # User cannot overlap their own bookings
    for bk in user_bookings_today:
        try:
            bk_start = datetime.fromisoformat(bk["start_time"])
        except Exception:
            continue

        if bk.get("end_time"):
            try:
                bk_end = datetime.fromisoformat(bk["end_time"])
            except Exception:
                bk_end = bk_start + timedelta(minutes=svc_duration.get(bk.get("service_id"), 30))
        else:
            bk_end = bk_start + timedelta(minutes=svc_duration.get(bk.get("service_id"), 30))

        if _overlaps(bk_start, bk_end, start_dt, end_dt):
            return None, None, "You already have an appointment at this time. Cannot double-book."

    # Shop capacity per 30-min segment (max 2 concurrent per segment)
    segments = _slot_segments_30min(day, start_dt, end_dt)
    for seg_start, seg_end in segments:
        concurrent_count = 0
        for bk in existing:
            if booking_id and bk["id"] == booking_id:
                continue

            try:
                bk_start = datetime.fromisoformat(bk["start_time"])
            except Exception:
                continue

            if bk.get("end_time"):
                try:
                    bk_end = datetime.fromisoformat(bk["end_time"])
                except Exception:
                    bk_end = bk_start + timedelta(minutes=svc_duration.get(bk.get("service_id"), 30))
            else:
                bk_end = bk_start + timedelta(minutes=svc_duration.get(bk.get("service_id"), 30))

            if _overlaps(bk_start, bk_end, seg_start, seg_end):
                concurrent_count += 1

        if concurrent_count >= SHOP_CAPACITY_PER_SLOT:
            return None, None, "This time slot is fully booked. Please pick another time."

    return start_dt, end_dt, None


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

        # parse day + time
        try:
            day = date.fromisoformat(date_str)
            t_raw = time.fromisoformat(time_str)
            start_t = time(t_raw.hour, t_raw.minute)
        except Exception:
            return render_template(
                "appointments/form.html",
                appointment={},
                services=services,
                today_min=today_min,
                error="Invalid date/time.",
            )

        # load duration for capacity/hour validation + to set end_time
        svc = query_db(
            "SELECT duration_min FROM services WHERE id = ? AND is_active = 1",
            (service_id,),
            one=True,
        )
        if not svc:
            return render_template(
                "appointments/form.html",
                appointment={},
                services=services,
                today_min=today_min,
                error="Invalid service.",
            )

        duration_min = int(svc["duration_min"] or 30)

        start_dt, end_dt, err = _validate_customer_portal_booking(
            day=day,
            start_t=start_t,
            duration_min=duration_min,
            user_id=int(user_id),
            booking_id=None,
        )
        if err:
            return render_template(
                "appointments/form.html",
                appointment={},
                services=services,
                today_min=today_min,
                error=err,
            )

        now_iso = datetime.utcnow().isoformat(timespec="seconds")

        execute_db(
            """
            INSERT INTO appointments
                (user_id, customer_name, service_id, start_time, end_time, notes, status, created_at, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?, 'booked', ?, ?)
            """,
            (user_id, customer_name, service_id, _iso(start_dt), _iso(end_dt), notes, now_iso, now_iso),
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

        try:
            day = date.fromisoformat(date_str)
            t_raw = time.fromisoformat(time_str)
            start_t = time(t_raw.hour, t_raw.minute)
        except Exception:
            return render_template(
                "appointments/form.html",
                appointment=form_appt,
                services=services,
                today_min=today_min,
                error="Invalid date/time.",
            )

        svc = query_db(
            "SELECT duration_min FROM services WHERE id = ? AND is_active = 1",
            (service_id,),
            one=True,
        )
        if not svc:
            return render_template(
                "appointments/form.html",
                appointment=form_appt,
                services=services,
                today_min=today_min,
                error="Invalid service.",
            )

        duration_min = int(svc["duration_min"] or 30)

        start_dt, end_dt, err = _validate_customer_portal_booking(
            day=day,
            start_t=start_t,
            duration_min=duration_min,
            user_id=int(user_id),
            booking_id=int(appt_id),
        )
        if err:
            return render_template(
                "appointments/form.html",
                appointment=form_appt,
                services=services,
                today_min=today_min,
                error=err,
            )

        now_iso = datetime.utcnow().isoformat(timespec="seconds")

        execute_db(
            """
            UPDATE appointments
            SET customer_name = ?, service_id = ?, start_time = ?, end_time = ?, notes = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (customer_name, service_id, _iso(start_dt), _iso(end_dt), notes, now_iso, appt_id, user_id),
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
