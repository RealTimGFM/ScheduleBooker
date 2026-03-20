from __future__ import annotations

from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, session
from jinja2 import TemplateNotFound

from ..repositories import public_booking_repository as booking_repo
from ..services.booking_service import (
    MAX_BOOKINGS_PER_DAY_MESSAGE,
    SHOP_TIMEZONE,
    build_time_slots,
    count_bookings_for_contact,
    generate_booking_code,
    iso_datetime,
    normalize_contact,
    normalize_email,
    normalize_phone,
    parse_date_or_default,
    parse_time_hhmm,
    split_services_by_popularity,
    store_cancellation_and_mark_cancelled,
    validate_customer_cancellation_window,
    validate_public_booking,
)
from . import public_bp


def render_or_json(template_name: str, **ctx):
    try:
        return render_template(template_name, **ctx)
    except TemplateNotFound:
        return jsonify({"template": template_name, "context": ctx})


@public_bp.get("/services")
def services():
    most_popular_services, other_services = split_services_by_popularity()
    return render_or_json(
        "public/services.html",
        most_popular_services=most_popular_services,
        other_services=other_services,
        error=None,
    )


@public_bp.get("/book")
def book_schedule():
    min_date = datetime.now(SHOP_TIMEZONE).date().isoformat()

    service_id = request.args.get("service_id", type=int)
    selected_date_str = request.args.get("date")
    selected_barber_id = request.args.get("barber_id", type=int)
    barbers = booking_repo.list_active_barbers()

    if not service_id:
        return render_or_json(
            "public/book_schedule.html",
            service=None,
            barbers=barbers,
            selected_date=None,
            selected_barber_id=selected_barber_id,
            time_slots=[],
            min_date=min_date,
            error="service_id is required",
        )

    service = booking_repo.get_active_service(service_id)
    if not service:
        return render_or_json(
            "public/book_schedule.html",
            service=None,
            barbers=barbers,
            selected_date=None,
            selected_barber_id=selected_barber_id,
            time_slots=[],
            min_date=min_date,
            error="Invalid service_id",
        )

    selected_date_str, day = parse_date_or_default(selected_date_str)
    if not day:
        return render_or_json(
            "public/book_schedule.html",
            service=service,
            barbers=barbers,
            selected_date=None,
            selected_barber_id=selected_barber_id,
            time_slots=[],
            min_date=min_date,
            error="Invalid date format (expected YYYY-MM-DD)",
        )

    duration_min = int(service.get("duration_min") or 30)
    time_slots = build_time_slots(day, duration_min, barbers, selected_barber_id)

    return render_or_json(
        "public/book_schedule.html",
        service=service,
        barbers=barbers,
        selected_date=selected_date_str,
        selected_barber_id=selected_barber_id,
        time_slots=time_slots,
        min_date=min_date,
        error=None,
    )


@public_bp.post("/book/confirm")
def book_confirm():
    service_id = request.form.get("service_id", type=int)
    barber_id = request.form.get("barber_id", type=int)
    date_str = request.form.get("date", type=str)
    time_str = request.form.get("time", type=str)

    if not service_id or not date_str or not time_str:
        return render_or_json(
            "public/book_confirm.html",
            service=None,
            barber=None,
            date=date_str,
            time=time_str,
            duration_min=None,
            error="Missing required booking selection (service/date/time).",
        )

    service = booking_repo.get_active_service(service_id)
    if not service:
        return render_or_json(
            "public/book_confirm.html",
            service=None,
            barber=None,
            date=date_str,
            time=time_str,
            duration_min=None,
            error="Invalid service selection.",
        )

    barber = booking_repo.get_active_barber(barber_id) if barber_id else None
    if barber_id and not barber:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=None,
            date=date_str,
            time=time_str,
            duration_min=int(service.get("duration_min") or 30),
            error="Invalid barber selection.",
        )

    return render_or_json(
        "public/book_confirm.html",
        service=service,
        barber=barber,
        date=date_str,
        time=time_str,
        duration_min=int(service.get("duration_min") or 30),
        error=None,
    )


@public_bp.post("/book/finish")
def book_finish():
    service_id = request.form.get("service_id", type=int)
    barber_id = request.form.get("barber_id", type=int)
    date_str = request.form.get("date", type=str)
    time_str = request.form.get("time", type=str)

    customer_name = (request.form.get("customer_name") or "").strip()
    customer_phone_raw = request.form.get("customer_phone")
    customer_email_raw = request.form.get("customer_email")
    notes = (request.form.get("notes") or "").strip()

    service = booking_repo.get_active_service(service_id) if service_id else None
    barber = booking_repo.get_active_barber(barber_id) if barber_id else None
    duration_min = int(service.get("duration_min") or 30) if service else None

    if not service or not date_str or not time_str:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=barber,
            date=date_str,
            time=time_str,
            duration_min=duration_min,
            error="Missing or invalid booking selection.",
        )

    if barber_id and not barber:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=None,
            date=date_str,
            time=time_str,
            duration_min=duration_min,
            error="Invalid barber selection.",
        )

    if not customer_name:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=barber,
            date=date_str,
            time=time_str,
            duration_min=duration_min,
            error="Customer name is required.",
        )

    customer_phone = normalize_phone(customer_phone_raw)
    customer_email = normalize_email(customer_email_raw)
    if not customer_phone and not customer_email:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=barber,
            date=date_str,
            time=time_str,
            duration_min=duration_min,
            error="Phone or email is required.",
        )

    _, day = parse_date_or_default(date_str)
    start_t = parse_time_hhmm(time_str)
    if not day or not start_t:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=barber,
            date=date_str,
            time=time_str,
            duration_min=duration_min,
            error="Invalid date or time format.",
        )

    if count_bookings_for_contact(day, customer_phone, customer_email) >= 2:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=barber,
            date=date_str,
            time=time_str,
            duration_min=duration_min,
            error=MAX_BOOKINGS_PER_DAY_MESSAGE,
        )

    start_dt, end_dt, err = validate_public_booking(
        service=service,
        barber=barber,
        day=day,
        start_t=start_t,
        user_id=session.get("user_id"),
    )
    if err:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=barber,
            date=date_str,
            time=time_str,
            duration_min=duration_min,
            error=err,
        )

    now = iso_datetime(datetime.now())
    booking_id = booking_repo.create_appointment(
        user_id=session.get("user_id"),
        barber_id=(barber["id"] if barber else None),
        service_id=service["id"],
        customer_name=customer_name,
        customer_phone=customer_phone or None,
        customer_email=customer_email,
        start_time_iso=iso_datetime(start_dt),
        end_time_iso=iso_datetime(end_dt),
        notes=notes,
        status="booked",
        booking_code=generate_booking_code(),
        created_at_iso=now,
        updated_at_iso=now,
    )
    flash("Booking confirmed.", "success")
    return redirect(f"/book/success?booking_id={booking_id}")


@public_bp.get("/book/success")
def book_success():
    booking_id = request.args.get("booking_id", type=int)
    if not booking_id:
        return render_or_json("public/book_success.html", booking=None, error="Missing booking_id.")

    booking = booking_repo.get_booking_with_details(booking_id)
    if not booking:
        return render_or_json("public/book_success.html", booking=None, error="Booking not found.")

    return render_or_json("public/book_success.html", booking=booking, error=None)


@public_bp.get("/find-booking")
def find_booking_page():
    return render_or_json("public/find_booking.html", contact="", error=None)


@public_bp.post("/find-booking")
def find_booking_results():
    contact = request.form.get("contact")
    phone, email = normalize_contact(contact)

    if not phone and not email:
        return render_or_json(
            "public/find_booking.html",
            contact="",
            error="Please enter a phone number or email.",
        )

    return render_or_json(
        "public/find_booking_results.html",
        contact=(contact or "").strip(),
        bookings=booking_repo.find_bookings_by_contact(phone, email),
        error=None,
    )


@public_bp.post("/booking/<int:booking_id>/cancel")
def cancel_booking(booking_id: int):
    contact = request.form.get("contact")
    booking_code = (request.form.get("booking_code") or "").strip()

    phone, email = normalize_contact(contact)
    bookings = booking_repo.find_bookings_by_contact(phone, email)

    if not booking_code or (not phone and not email):
        return render_or_json(
            "public/find_booking_results.html",
            contact=(contact or "").strip(),
            bookings=bookings,
            error="Contact and booking code are required.",
        )

    booking = booking_repo.get_booking_for_cancellation(booking_id, booked_only=True)
    if not booking:
        return render_or_json(
            "public/find_booking_results.html",
            contact=(contact or "").strip(),
            bookings=bookings,
            error="Booking not found.",
        )

    matches_contact = (phone and booking["customer_phone"] == phone) or (
        email and (booking["customer_email"] or "").lower() == email
    )
    matches_code = (booking["booking_code"] or "") == booking_code

    if not (matches_contact and matches_code):
        return render_or_json(
            "public/find_booking_results.html",
            contact=(contact or "").strip(),
            bookings=bookings,
            error="Invalid contact or booking code.",
        )

    cancel_error = validate_customer_cancellation_window(booking)
    if cancel_error:
        return render_or_json(
            "public/find_booking_results.html",
            contact=(contact or "").strip(),
            bookings=bookings,
            error=cancel_error,
        )

    store_cancellation_and_mark_cancelled(booking, "customer")
    return render_or_json(
        "public/find_booking_results.html",
        contact=(contact or "").strip(),
        bookings=booking_repo.find_bookings_by_contact(phone, email),
        error=None,
    )


@public_bp.get("/about")
def about_page():
    return redirect("/services#about")


@public_bp.get("/contact")
def contact_page():
    return redirect("/services#contact")


@public_bp.post("/api/booking/<int:booking_id>/cancel")
def cancel_booking_api(booking_id: int):
    data = request.get_json() or {}
    phone = normalize_phone(data.get("phone"))

    if not phone:
        return jsonify({"ok": False, "error": "Phone number is required."}), 400

    booking = booking_repo.get_booking_for_cancellation(booking_id, booked_only=True)
    if not booking:
        return jsonify({"ok": False, "error": "Booking not found or already cancelled."}), 404

    if normalize_phone(booking["customer_phone"]) != phone:
        return jsonify({"ok": False, "error": "Phone number does not match booking."}), 403

    cancel_error = validate_customer_cancellation_window(booking)
    if cancel_error:
        return jsonify({"ok": False, "error": cancel_error}), 400

    store_cancellation_and_mark_cancelled(booking, "customer")
    return jsonify({"ok": True, "booking_id": booking_id}), 200
