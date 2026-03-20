# schedulebooker/appointments/routes.py

from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, session, url_for

from ..repositories import appointments_repository as appt_repo
from ..repositories import public_booking_repository as booking_repo
from ..services.booking_service import (
    SHOP_TIMEZONE,
    floor_to_minute,
    iso_datetime,
    parse_time_hhmm,
    validate_customer_portal_booking,
)
from . import appointments_bp


def _validate_not_past(date_str: str | None, time_str: str | None) -> str | None:
    if not date_str or not time_str:
        return "Missing date/time."

    try:
        d = date.fromisoformat(date_str)
        t = parse_time_hhmm(time_str)
        if t is None:
            raise ValueError
    except Exception:
        return "Invalid date/time."

    requested = floor_to_minute(datetime.combine(d, t, tzinfo=SHOP_TIMEZONE))
    now = floor_to_minute(datetime.now(SHOP_TIMEZONE))

    if requested < now:
        return "Cannot book in the past."

    return None


@appointments_bp.route("/")
def list_appointments():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    user = appt_repo.get_user_phone(int(user_id))
    phone = None
    if user is not None:
        try:
            phone = user["phone_number"]
        except Exception:
            phone = None

    if phone:
        appt_repo.claim_guest_bookings_for_phone(int(user_id), phone)

    appts = appt_repo.list_user_appointments(int(user_id))

    return render_template("appointments/list.html", appointments=appts, appts=appts)


@appointments_bp.route("/new", methods=["GET", "POST"])
def new_appointment():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    svc_rows = appt_repo.list_service_choices()
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

        try:
            day = date.fromisoformat(date_str)
            start_t = parse_time_hhmm(time_str)
            if start_t is None:
                raise ValueError
        except Exception:
            return render_template(
                "appointments/form.html",
                appointment={},
                services=services,
                today_min=today_min,
                error="Invalid date/time.",
            )

        svc = booking_repo.get_active_service(service_id)
        if not svc:
            return render_template(
                "appointments/form.html",
                appointment={},
                services=services,
                today_min=today_min,
                error="Invalid service.",
            )

        start_dt, end_dt, err = validate_customer_portal_booking(
            day=day,
            start_t=start_t,
            duration_min=int(svc["duration_min"] or 30),
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
        appt_repo.create_user_appointment(
            user_id=int(user_id),
            customer_name=customer_name,
            service_id=service_id,
            start_time=iso_datetime(start_dt),
            end_time=iso_datetime(end_dt),
            notes=notes,
            created_at=now_iso,
            updated_at=now_iso,
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

    appt = appt_repo.get_user_appointment(int(appt_id), int(user_id))
    if not appt:
        abort(404)

    svc_rows = appt_repo.list_service_choices()
    services = [(r["id"], r["name"]) for r in svc_rows]
    today_min = datetime.now(SHOP_TIMEZONE).date().isoformat()

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        service_id = request.form.get("service_id", type=int)
        date_str = request.form.get("date")
        time_str = request.form.get("time")
        notes = request.form.get("notes", "")

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
            start_t = parse_time_hhmm(time_str)
            if start_t is None:
                raise ValueError
        except Exception:
            return render_template(
                "appointments/form.html",
                appointment=form_appt,
                services=services,
                today_min=today_min,
                error="Invalid date/time.",
            )

        svc = booking_repo.get_active_service(service_id)
        if not svc:
            return render_template(
                "appointments/form.html",
                appointment=form_appt,
                services=services,
                today_min=today_min,
                error="Invalid service.",
            )

        start_dt, end_dt, err = validate_customer_portal_booking(
            day=day,
            start_t=start_t,
            duration_min=int(svc["duration_min"] or 30),
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
        appt_repo.update_user_appointment(
            appt_id=int(appt_id),
            user_id=int(user_id),
            customer_name=customer_name,
            service_id=service_id,
            start_time=iso_datetime(start_dt),
            end_time=iso_datetime(end_dt),
            notes=notes,
            updated_at=now_iso,
        )
        flash("Appointment updated.", "success")
        return redirect(url_for("appointments.list_appointments"))

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

    appt_repo.delete_user_appointment(int(appt_id), int(user_id))
    return redirect(url_for("appointments.list_appointments"))
