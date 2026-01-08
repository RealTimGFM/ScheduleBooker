from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import flash, jsonify, redirect, render_template, request, session
from jinja2 import TemplateNotFound

from ..sqlite_db import execute_db, query_db
from . import public_bp
from ..extensions import limiter

SHOP_CAPACITY_PER_SLOT = 2  # Public capacity limit
SHOP_TIMEZONE = ZoneInfo("America/Toronto")  # Montreal timezone
OPEN = time(11, 0)
CLOSE = time(19, 0)
LAST_END_TIME = time(18, 30)  # Last appointment must END by 18:30
MAX_BOOKINGS_PER_DAY_MESSAGE = (
    "If you want more than 2 bookings in a day, contact the barber."
)


def render_or_json(template_name: str, **ctx):
    try:
        return render_template(template_name, **ctx)
    except TemplateNotFound:
        return jsonify({"template": template_name, "context": ctx})


def _parse_date_or_default(
    date_str: str | None,
) -> tuple[str, date] | tuple[None, None]:
    if not date_str:
        d = datetime.now(SHOP_TIMEZONE).date()
        return d.isoformat(), d
    try:
        d = date.fromisoformat(date_str)
        return date_str, d
    except ValueError:
        return None, None


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(timespec="seconds")


def _floor_to_minute(dt: datetime) -> datetime:
    """Normalize datetimes to minute precision (drop seconds/microseconds)."""
    return dt.replace(second=0, microsecond=0)


def _overlaps(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    return a_start < b_end and a_end > b_start


def _load_services_split():
    rows = query_db(
        "SELECT id, name, category, duration_min, price, price_is_from, price_label, is_popular "
        "FROM services WHERE is_active = 1 "
        "ORDER BY sort_order ASC, name ASC"
    )
    services = [dict(r) for r in rows]
    most = [s for s in services if s.get("is_popular") == 1]
    other = [s for s in services if s.get("is_popular") != 1]
    return most, other


def _load_active_barbers():
    rows = query_db(
        "SELECT id, name, is_active FROM barbers WHERE is_active = 1 ORDER BY name ASC"
    )
    return [dict(r) for r in rows]


def _load_service(service_id: int):
    row = query_db(
        "SELECT id, name, category, duration_min, price, price_is_from, price_label "
        "FROM services WHERE id = ? AND is_active = 1",
        (service_id,),
        one=True,
    )
    return dict(row) if row else None


def _load_bookings_for_day(day: date):
    day_start = datetime.combine(day, time(0, 0))
    day_end = day_start + timedelta(days=1)

    rows = query_db(
        """
        SELECT id, barber_id, service_id, start_time, end_time, status, customer_phone, customer_email, user_id
        FROM appointments
        WHERE status != 'cancelled' AND start_time >= ? AND start_time < ?
        """,
        (_iso(day_start), _iso(day_end)),
    )
    return [dict(r) for r in rows]


def _validate_shop_hours_and_past(day: date, start_t: time, end_t: time) -> str | None:
    """
    Shared validation: shop hours, Monday closed, end_time <= 18:30, no past bookings.
    Returns error message or None.
    """
    # Monday closed
    if day.weekday() == 0:
        return "Shop is closed on Monday."

    # Check if booking is in the past (shop timezone) — minute precision
    now = _floor_to_minute(datetime.now(SHOP_TIMEZONE))
    booking_datetime = _floor_to_minute(
        datetime.combine(day, start_t, tzinfo=SHOP_TIMEZONE)
    )

    if booking_datetime < now:
        return "Cannot book in the past."

    # Shop hours: start must be >= 11:00 and < 19:00
    if start_t < OPEN or start_t >= CLOSE:
        return f"Start time must be between {OPEN.strftime('%H:%M')} and {CLOSE.strftime('%H:%M')}."

    # End time must be <= 18:30
    if end_t > LAST_END_TIME:
        return f"Booking ends at {end_t.strftime('%H:%M')}, but last appointment must end by {LAST_END_TIME.strftime('%H:%M')}."

    return None


def _build_time_slots(
    day: date, duration_min: int, barbers: list[dict], selected_barber_id: int | None
):
    # Monday closed
    if day.weekday() == 0:
        slots = []
        t = datetime.combine(day, OPEN)
        end = datetime.combine(day, CLOSE)
        while t < end:
            slots.append(
                {
                    "time": t.strftime("%H:%M"),
                    "is_available": False,
                    "reason": "Closed (Monday)",
                }
            )
            t += timedelta(minutes=30)
        return slots

    active_barber_ids = [b["id"] for b in barbers]
    if selected_barber_id is not None and selected_barber_id not in active_barber_ids:
        return [{"time": "11:00", "is_available": False, "reason": "Invalid barber"}]

    bookings = _load_bookings_for_day(day)

    # Build service duration lookup for bookings
    svc_rows = query_db("SELECT id, duration_min FROM services")
    svc_duration = {r["id"]: r["duration_min"] for r in svc_rows}

    parsed = []
    for bk in bookings:
        try:
            st = datetime.fromisoformat(bk["start_time"])
        except Exception:
            continue

        if bk.get("end_time"):
            try:
                en = datetime.fromisoformat(bk["end_time"])
            except Exception:
                en = st + timedelta(minutes=svc_duration.get(bk.get("service_id"), 30))
        else:
            en = st + timedelta(minutes=svc_duration.get(bk.get("service_id"), 30))

        parsed.append({"barber_id": bk.get("barber_id"), "start": st, "end": en})

    effective_shop_cap = (
        min(SHOP_CAPACITY_PER_SLOT, len(active_barber_ids)) if active_barber_ids else 0
    )

    slots = []
    cursor = datetime.combine(day, OPEN)
    last_start = datetime.combine(day, LAST_END_TIME) - timedelta(minutes=duration_min)

    now = datetime.now(SHOP_TIMEZONE).replace(second=0, microsecond=0)

    while cursor <= last_start:
        slot_start = cursor
        slot_end = cursor + timedelta(minutes=duration_min)

        # Check if slot is in the past (minute precision, shop timezone)
        slot_datetime = slot_start.replace(tzinfo=SHOP_TIMEZONE).replace(
            second=0, microsecond=0
        )
        if slot_datetime < now:
            slots.append(
                {
                    "time": slot_start.strftime("%H:%M"),
                    "is_available": False,
                    "reason": "Past",
                }
            )
            cursor += timedelta(minutes=30)
            continue

        # Count overlaps shop-wide
        shop_overlaps = 0
        for p in parsed:
            if _overlaps(p["start"], p["end"], slot_start, slot_end):
                shop_overlaps += 1

        if effective_shop_cap == 0:
            slots.append(
                {
                    "time": slot_start.strftime("%H:%M"),
                    "is_available": False,
                    "reason": "No barbers",
                }
            )
            cursor += timedelta(minutes=30)
            continue

        if shop_overlaps >= effective_shop_cap:
            slots.append(
                {
                    "time": slot_start.strftime("%H:%M"),
                    "is_available": False,
                    "reason": "Full",
                }
            )
            cursor += timedelta(minutes=30)
            continue

        def barber_free(bid: int) -> bool:
            for p in parsed:
                if p["barber_id"] == bid and _overlaps(
                    p["start"], p["end"], slot_start, slot_end
                ):
                    return False
            return True

        if selected_barber_id is not None:
            ok = barber_free(selected_barber_id)
            slots.append(
                {
                    "time": slot_start.strftime("%H:%M"),
                    "is_available": ok,
                    "reason": None if ok else "Booked",
                }
            )
        else:
            ok_any = any(barber_free(bid) for bid in active_barber_ids)
            slots.append(
                {
                    "time": slot_start.strftime("%H:%M"),
                    "is_available": ok_any,
                    "reason": None if ok_any else "Booked",
                }
            )

        cursor += timedelta(minutes=30)

    return slots


def _load_barber(barber_id: int):
    row = query_db(
        "SELECT id, name, is_active FROM barbers WHERE id = ? AND is_active = 1",
        (barber_id,),
        one=True,
    )
    return dict(row) if row else None


def _normalize_phone(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _normalize_email(email: str | None) -> str | None:
    e = (email or "").strip().lower()
    return e or None


def _parse_time_hhmm(time_str: str | None) -> time | None:
    if not time_str:
        return None
    try:
        t = time.fromisoformat(time_str)
        return time(t.hour, t.minute)
    except ValueError:
        return None


def _validate_public_booking(
    service: dict,
    barber: dict,
    day: date,
    start_t: time,
    user_id: int | None,
    booking_id: int | None = None,
):
    """
    Public booking validation:
    - Shop hours, Monday, end_time <= 18:30, no past
    - User cannot have overlapping appointments
    - User cannot exceed 2 appointments per day
    - Shop capacity (max 2 concurrent)
    """
    duration_min = int(service.get("duration_min") or 30)
    start_dt = datetime.combine(day, start_t)
    end_dt = start_dt + timedelta(minutes=duration_min)

    # Validate shop hours and past
    hours_error = _validate_shop_hours_and_past(day, start_t, end_dt.time())
    if hours_error:
        return None, None, hours_error

    # Get all bookings for the day
    existing = _load_bookings_for_day(day)
    svc_rows = query_db("SELECT id, duration_min FROM services")
    svc_duration = {r["id"]: r["duration_min"] for r in svc_rows}

    # Check user constraints (if logged in)
    if user_id:
        user_bookings_today = [
            b
            for b in existing
            if b.get("user_id") == user_id and (not booking_id or b["id"] != booking_id)
        ]

        # Check daily max (2 appointments)
        if len(user_bookings_today) >= 2:
            return None, None, MAX_BOOKINGS_PER_DAY_MESSAGE

        # Check for overlapping appointments for this user
        for bk in user_bookings_today:
            try:
                bk_start = datetime.fromisoformat(bk["start_time"])
            except Exception:
                continue

            if bk.get("end_time"):
                try:
                    bk_end = datetime.fromisoformat(bk["end_time"])
                except Exception:
                    bk_end = bk_start + timedelta(
                        minutes=svc_duration.get(bk.get("service_id"), 30)
                    )
            else:
                bk_end = bk_start + timedelta(
                    minutes=svc_duration.get(bk.get("service_id"), 30)
                )

            if _overlaps(bk_start, bk_end, start_dt, end_dt):
                return (
                    None,
                    None,
                    "You already have an appointment at this time. Cannot double-book.",
                )

    # Check barber overlap
    for bk in existing:
        if booking_id and bk["id"] == booking_id:
            continue

        if bk.get("barber_id") != barber["id"]:
            continue

        try:
            bk_start = datetime.fromisoformat(bk["start_time"])
        except Exception:
            continue

        if bk.get("end_time"):
            try:
                bk_end = datetime.fromisoformat(bk["end_time"])
            except Exception:
                bk_end = bk_start + timedelta(
                    minutes=svc_duration.get(bk.get("service_id"), 30)
                )
        else:
            bk_end = bk_start + timedelta(
                minutes=svc_duration.get(bk.get("service_id"), 30)
            )

        if _overlaps(bk_start, bk_end, start_dt, end_dt):
            return (
                None,
                None,
                "That time is no longer available. Please choose another slot.",
            )

    # Check shop capacity (public bookings only, max 2 concurrent)
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
                bk_end = bk_start + timedelta(
                    minutes=svc_duration.get(bk.get("service_id"), 30)
                )
        else:
            bk_end = bk_start + timedelta(
                minutes=svc_duration.get(bk.get("service_id"), 30)
            )

        if _overlaps(bk_start, bk_end, start_dt, end_dt):
            concurrent_count += 1

    if concurrent_count >= SHOP_CAPACITY_PER_SLOT:
        return None, None, "This time slot is fully booked. Please choose another time."

    return start_dt, end_dt, None


def _count_bookings_for_contact(day: date, phone: str | None, email: str | None) -> int:
    day_start = datetime.combine(day, time(0, 0))
    day_end = day_start + timedelta(days=1)

    phone = _normalize_phone(phone) if phone else ""
    email = _normalize_email(email)

    clauses = []
    args: list[object] = [_iso(day_start), _iso(day_end)]

    if phone:
        clauses.append("customer_phone = ?")
        args.append(phone)
    if email:
        clauses.append("customer_email = ?")
        args.append(email)

    if not clauses:
        return 0

    where_contact = " OR ".join(clauses)

    row = query_db(
        "SELECT COUNT(*) AS cnt FROM appointments "
        "WHERE status != 'cancelled' AND start_time >= ? AND start_time < ? "
        f"AND ({where_contact})",
        tuple(args),
        one=True,
    )
    return int(row["cnt"]) if row else 0


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


def _normalize_contact(contact: str | None) -> tuple[str | None, str | None]:
    c = (contact or "").strip()
    if not c:
        return None, None
    if "@" in c:
        return None, c.lower()
    digits = "".join(ch for ch in c if ch.isdigit())
    return (digits or None), None


def _find_bookings_by_contact(phone: str | None, email: str | None) -> list[dict]:
    if not phone and not email:
        return []

    clauses = []
    args: list[object] = []
    if phone:
        clauses.append("customer_phone = ?")
        args.append(phone)
    if email:
        clauses.append("customer_email = ?")
        args.append(email)

    where_contact = " OR ".join(clauses)

    rows = query_db(
        "SELECT a.id, a.start_time, a.end_time, a.status, a.service_id, a.barber_id, "
        "       a.customer_name, a.customer_phone, a.customer_email, a.notes, "
        "       s.name AS service_name, b.name AS barber_name "
        "FROM appointments a "
        "LEFT JOIN services s ON s.id = a.service_id "
        "LEFT JOIN barbers b ON b.id = a.barber_id "
        f"WHERE ({where_contact}) "
        "ORDER BY a.start_time DESC",
        tuple(args),
    )
    return [dict(r) for r in rows]


@public_bp.get("/services")
def services():
    most_popular_services, other_services = _load_services_split()
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

    if not service_id:
        return render_or_json(
            "public/book_schedule.html",
            service=None,
            barbers=_load_active_barbers(),
            selected_date=None,
            selected_barber_id=selected_barber_id,
            time_slots=[],
            min_date=min_date,
            error="service_id is required",
        )

    service = _load_service(service_id)
    if not service:
        return render_or_json(
            "public/book_schedule.html",
            service=None,
            barbers=_load_active_barbers(),
            selected_date=None,
            selected_barber_id=selected_barber_id,
            time_slots=[],
            min_date=min_date,
            error="Invalid service_id",
        )

    barbers = _load_active_barbers()

    selected_date_str, day = _parse_date_or_default(selected_date_str)
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
    time_slots = _build_time_slots(day, duration_min, barbers, selected_barber_id)

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

    if not service_id or not barber_id or not date_str or not time_str:
        return render_or_json(
            "public/book_confirm.html",
            service=None,
            barber=None,
            date=date_str,
            time=time_str,
            duration_min=None,
            error="Missing required booking selection (service/barber/date/time).",
        )

    service = _load_service(service_id)
    barber = _load_barber(barber_id)

    if not service or not barber:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=barber,
            date=date_str,
            time=time_str,
            duration_min=int(service.get("duration_min") or 30) if service else None,
            error="Invalid service or barber selection.",
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
@limiter.limit("30 per hour")
def book_finish():
    service_id = request.form.get("service_id", type=int)
    barber_id = request.form.get("barber_id", type=int)
    date_str = request.form.get("date", type=str)
    time_str = request.form.get("time", type=str)

    customer_name = (request.form.get("customer_name") or "").strip()
    customer_phone_raw = request.form.get("customer_phone")
    customer_email_raw = request.form.get("customer_email")
    notes = (request.form.get("notes") or "").strip()

    service = _load_service(service_id) if service_id else None
    barber = _load_barber(barber_id) if barber_id else None
    duration_min = int(service.get("duration_min") or 30) if service else None

    if not service or not barber or not date_str or not time_str:
        return render_or_json(
            "public/book_confirm.html",
            service=service,
            barber=barber,
            date=date_str,
            time=time_str,
            duration_min=duration_min,
            error="Missing or invalid booking selection.",
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

    customer_phone = _normalize_phone(customer_phone_raw)
    customer_email = _normalize_email(customer_email_raw)
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

    _, day = _parse_date_or_default(date_str)
    start_t = _parse_time_hhmm(time_str)
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

    user_id = session.get("user_id")
    start_dt, end_dt, err = _validate_public_booking(
        service, barber, day, start_t, user_id
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

    now = _iso(datetime.now())
    booking_code = _generate_booking_code()

    booking_id = execute_db(
        "INSERT INTO appointments "
        "(user_id, barber_id, service_id, customer_name, customer_phone, customer_email, "
        " start_time, end_time, notes, status, booking_code, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            barber["id"],
            service["id"],
            customer_name,
            customer_phone or None,
            customer_email,
            _iso(start_dt),
            _iso(end_dt),
            notes,
            "booked",
            booking_code,
            now,
            now,
        ),
    )
    flash("Booking confirmed.", "success")
    return redirect(f"/book/success?booking_id={booking_id}")


@public_bp.get("/book/success")
def book_success():
    booking_id = request.args.get("booking_id", type=int)
    if not booking_id:
        return render_or_json(
            "public/book_success.html", booking=None, error="Missing booking_id."
        )

    row = query_db(
        "SELECT a.*, s.name AS service_name, b.name AS barber_name "
        "FROM appointments a "
        "LEFT JOIN services s ON s.id = a.service_id "
        "LEFT JOIN barbers b ON b.id = a.barber_id "
        "WHERE a.id = ?",
        (booking_id,),
        one=True,
    )
    booking = dict(row) if row else None

    if not booking:
        return render_or_json(
            "public/book_success.html", booking=None, error="Booking not found."
        )

    return render_or_json("public/book_success.html", booking=booking, error=None)


@public_bp.get("/find-booking")
def find_booking_page():
    return render_or_json("public/find_booking.html", contact="", error=None)


@public_bp.post("/find-booking")
@limiter.limit("30 per hour")
def find_booking_results():
    contact = request.form.get("contact")
    booking_code = (request.form.get("booking_code") or "").strip()

    phone, email = _normalize_contact(contact)

    if not phone and not email:
        return render_or_json(
            "public/find_booking.html",
            contact="",
            booking_code="",
            error="Please enter a phone number or email.",
        )

    # REQUIRE booking_code for lookup
    if not booking_code:
        return render_or_json(
            "public/find_booking.html",
            contact=contact.strip(),
            booking_code="",
            error="Please enter your booking code to view bookings.",
        )

    # Find bookings matching BOTH contact AND booking_code
    bookings = _find_bookings_by_contact_and_code(phone, email, booking_code)

    return render_or_json(
        "public/find_booking_results.html",
        contact=(contact or "").strip(),
        booking_code=booking_code,
        bookings=bookings,
        error=None,
    )


def _find_bookings_by_contact_and_code(
    phone: str | None, email: str | None, booking_code: str
) -> list[dict]:
    """Find bookings matching contact AND booking_code."""
    if not phone and not email:
        return []

    clauses = []
    args: list[object] = []

    if phone:
        clauses.append("customer_phone = ?")
        args.append(phone)
    if email:
        clauses.append("customer_email = ?")
        args.append(email)

    # CRITICAL: Also require booking_code match
    where_contact = " OR ".join(clauses)
    args.append(booking_code)  # Add booking_code to query

    rows = query_db(
        "SELECT a.id, a.start_time, a.end_time, a.status, a.service_id, a.barber_id, "
        "       a.customer_name, a.customer_phone, a.customer_email, a.notes, "
        "       s.name AS service_name, b.name AS barber_name "
        "FROM appointments a "
        "LEFT JOIN services s ON s.id = a.service_id "
        "LEFT JOIN barbers b ON b.id = a.barber_id "
        f"WHERE ({where_contact}) AND a.booking_code = ? "
        "ORDER BY a.start_time DESC",
        tuple(args),
    )
    return [dict(r) for r in rows]


@public_bp.post("/booking/<int:booking_id>/cancel")
def cancel_booking(booking_id: int):
    contact = request.form.get("contact")
    booking_code = (request.form.get("booking_code") or "").strip()

    phone, email = _normalize_contact(contact)

    if not booking_code or (not phone and not email):
        bookings = _find_bookings_by_contact(phone, email)
        return render_or_json(
            "public/find_booking_results.html",
            contact=(contact or "").strip(),
            bookings=bookings,
            error="Contact and booking code are required.",
        )

    booking = query_db(
        "SELECT id, customer_phone, customer_email, booking_code, status "
        "FROM appointments WHERE id = ?",
        (booking_id,),
        one=True,
    )
    if not booking:
        bookings = _find_bookings_by_contact(phone, email)
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
        bookings = _find_bookings_by_contact(phone, email)
        return render_or_json(
            "public/find_booking_results.html",
            contact=(contact or "").strip(),
            bookings=bookings,
            error="Invalid contact or booking code.",
        )

    execute_db(
        "UPDATE appointments SET status = 'cancelled', updated_at = ? WHERE id = ?",
        (_iso(datetime.now()), booking_id),
    )

    bookings = _find_bookings_by_contact(phone, email)
    return render_or_json(
        "public/find_booking_results.html",
        contact=(contact or "").strip(),
        bookings=bookings,
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
    """API endpoint for customer cancellation with phone verification."""
    data = request.get_json() or {}
    phone = _normalize_phone(data.get("phone"))

    if not phone:
        return jsonify({"ok": False, "error": "Phone number is required."}), 400

    # Find booking
    booking = query_db(
        """
        SELECT a.*, s.name AS service_name, b.name AS barber_name
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN barbers b ON a.barber_id = b.id
        WHERE a.id = ? AND a.status = 'booked'
        """,
        (booking_id,),
        one=True,
    )

    if not booking:
        return (
            jsonify({"ok": False, "error": "Booking not found or already cancelled."}),
            404,
        )

    # Verify phone matches
    if _normalize_phone(booking["customer_phone"]) != phone:
        return (
            jsonify({"ok": False, "error": "Phone number does not match booking."}),
            403,
        )

    # Parse start time
    try:
        start_dt = datetime.fromisoformat(booking["start_time"])
    except Exception:
        return jsonify({"ok": False, "error": "Invalid booking date/time."}), 500

    # Check if booking is in the past
    now = _floor_to_minute(datetime.now(SHOP_TIMEZONE))
    booking_start = _floor_to_minute(start_dt.replace(tzinfo=SHOP_TIMEZONE))

    if booking_start < now:
        return jsonify({"ok": False, "error": "Cannot cancel past bookings."}), 400

    # Check if within 30 minutes
    time_until_start = (booking_start - now).total_seconds() / 60
    if time_until_start < 30:
        return (
            jsonify(
                {"ok": False, "error": "Cannot cancel within 30 minutes of start time."}
            ),
            400,
        )

    # Insert cancellation record
    cancelled_at = _iso(datetime.now())
    execute_db(
        """
        INSERT INTO cancellations
        (booking_id, customer_name, customer_phone, customer_email,
        barber_id, barber_name, service_id, service_name,
        start_datetime, end_datetime, cancelled_at, cancelled_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            booking_id,
            booking["customer_name"],
            booking["customer_phone"],
            booking["customer_email"],
            booking["barber_id"],
            booking["barber_name"],
            booking["service_id"],
            booking["service_name"],
            booking["start_time"],
            booking["end_time"],
            cancelled_at,
            "customer",
        ),
    )

    # Hard delete booking
    execute_db("DELETE FROM appointments WHERE id = ?", (booking_id,))

    return jsonify({"ok": True, "booking_id": booking_id}), 200
