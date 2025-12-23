from __future__ import annotations

from datetime import date, datetime, time, timedelta

from flask import jsonify, render_template, request
from jinja2 import TemplateNotFound

from ..sqlite_db import query_db
from . import public_bp

import secrets
from flask import redirect, session
from ..sqlite_db import execute_db



SHOP_CAPACITY_PER_SLOT = 3  # safe default; can be changed later
OPEN = time(11, 0)
CLOSE = time(19, 0)
MAX_BOOKINGS_PER_DAY_MESSAGE = "If you want more than 2 bookings in a day, contact the barber."


def render_or_json(template_name: str, **ctx):
    try:
        return render_template(template_name, **ctx)
    except TemplateNotFound:
        return jsonify({"template": template_name, "context": ctx})


def _parse_date_or_default(date_str: str | None) -> tuple[str, date] | tuple[None, None]:
    if not date_str:
        d = datetime.now().date()
        return d.isoformat(), d
    try:
        d = date.fromisoformat(date_str)
        return date_str, d
    except ValueError:
        return None, None


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
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
    rows = query_db("SELECT id, name, is_active FROM barbers WHERE is_active = 1 ORDER BY name ASC")
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
        "SELECT id, barber_id, service_id, start_time, end_time, status, customer_phone, customer_email "
        "FROM appointments "
        "WHERE status != 'cancelled' AND start_time >= ? AND start_time < ?",
        (_iso(day_start), _iso(day_end)),
    )
    return [dict(r) for r in rows]


def _build_time_slots(
    day: date, duration_min: int, barbers: list[dict], selected_barber_id: int | None
):
    # Monday closed (weekday: Mon=0)
    OPEN = time(11, 0)
    CLOSE = time(19, 0)

    if day.weekday() == 0:
        # still produce the grid so UI can show it greyed out
        slots = []
        t = datetime.combine(day, OPEN)
        end = datetime.combine(day, CLOSE)
        while t < end:
            slots.append(
                {"time": t.strftime("%H:%M"), "is_available": False, "reason": "Closed (Monday)"}
            )
            t += timedelta(minutes=30)
        return slots

    active_barber_ids = [b["id"] for b in barbers]
    if selected_barber_id is not None and selected_barber_id not in active_barber_ids:
        return [{"time": "11:00", "is_available": False, "reason": "Invalid barber"}]

    bookings = _load_bookings_for_day(day)

    # Build service duration lookup for bookings that have missing end_time
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

        parsed.append(
            {
                "barber_id": bk.get("barber_id"),
                "start": st,
                "end": en,
            }
        )

    # effective shop cap cannot exceed number of active barbers
    effective_shop_cap = (
        min(SHOP_CAPACITY_PER_SLOT, len(active_barber_ids)) if active_barber_ids else 0
    )

    slots = []
    cursor = datetime.combine(day, OPEN)
    last_start = datetime.combine(day, CLOSE) - timedelta(minutes=duration_min)

    while cursor <= last_start:
        slot_start = cursor
        slot_end = cursor + timedelta(minutes=duration_min)

        # count overlaps shop-wide
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
                {"time": slot_start.strftime("%H:%M"), "is_available": False, "reason": "Full"}
            )
            cursor += timedelta(minutes=30)
            continue

        # barber-specific availability
        def barber_free(bid: int) -> bool:
            for p in parsed:
                if p["barber_id"] == bid and _overlaps(p["start"], p["end"], slot_start, slot_end):
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
        t = time.fromisoformat(time_str)  # accepts HH:MM
        return time(t.hour, t.minute)
    except ValueError:
        return None
def _validate_public_booking(service: dict, barber: dict, day: date, start_t: time):
    duration_min = int(service.get("duration_min") or 30)

    if day.weekday() == 0:
        return None, None, "Closed (Monday)"

    if start_t.minute not in (0, 30):
        return None, None, "Time must be on a 30-minute grid (e.g., 11:00, 11:30)."

    start_dt = datetime.combine(day, start_t)
    end_dt = start_dt + timedelta(minutes=duration_min)

    open_dt = datetime.combine(day, OPEN)
    close_dt = datetime.combine(day, CLOSE)
    if start_dt < open_dt or end_dt > close_dt:
        return None, None, "Outside shop hours (Tue–Sun 11:00–19:00)."

    # overlap check
    existing = _load_bookings_for_day(day)
    svc_rows = query_db("SELECT id, duration_min FROM services")
    svc_duration = {r["id"]: r["duration_min"] for r in svc_rows}

    for bk in existing:
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
                bk_end = bk_start + timedelta(minutes=svc_duration.get(bk.get("service_id"), 30))
        else:
            bk_end = bk_start + timedelta(minutes=svc_duration.get(bk.get("service_id"), 30))

        if _overlaps(bk_start, bk_end, start_dt, end_dt):
            return None, None, "That time is no longer available. Please choose another slot."

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
    # phone
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
            service=None, barber=None, date=date_str, time=time_str, duration_min=None,
            error="Missing required booking selection (service/barber/date/time).",
        )

    service = _load_service(service_id)
    barber = _load_barber(barber_id)

    if not service or not barber:
        return render_or_json(
            "public/book_confirm.html",
            service=service, barber=barber, date=date_str, time=time_str,
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
            service=service, barber=barber, date=date_str, time=time_str, duration_min=duration_min,
            error="Missing or invalid booking selection.",
        )

    if not customer_name:
        return render_or_json(
            "public/book_confirm.html",
            service=service, barber=barber, date=date_str, time=time_str, duration_min=duration_min,
            error="Customer name is required.",
        )

    customer_phone = _normalize_phone(customer_phone_raw)
    customer_email = _normalize_email(customer_email_raw)
    if not customer_phone and not customer_email:
        return render_or_json(
            "public/book_confirm.html",
            service=service, barber=barber, date=date_str, time=time_str, duration_min=duration_min,
            error="Phone or email is required.",
        )

    _, day = _parse_date_or_default(date_str)
    start_t = _parse_time_hhmm(time_str)
    if not day or not start_t:
        return render_or_json(
            "public/book_confirm.html",
            service=service, barber=barber, date=date_str, time=time_str, duration_min=duration_min,
            error="Invalid date or time format.",
        )

    start_dt, end_dt, err = _validate_public_booking(service, barber, day, start_t)
    if err:
        return render_or_json(
            "public/book_confirm.html",
            service=service, barber=barber, date=date_str, time=time_str, duration_min=duration_min,
            error=err,
        )

    if _count_bookings_for_contact(day, customer_phone, customer_email) >= 2:
        return render_or_json(
            "public/book_confirm.html",
            service=service, barber=barber, date=date_str, time=time_str, duration_min=duration_min,
            error=MAX_BOOKINGS_PER_DAY_MESSAGE,
        )

    now = _iso(datetime.now())
    booking_code = _generate_booking_code()
    user_id = session.get("user_id")  # guest allowed if None

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

    return redirect(f"/book/success?booking_id={booking_id}")
@public_bp.get("/book/success")
def book_success():
    booking_id = request.args.get("booking_id", type=int)
    if not booking_id:
        return render_or_json("public/book_success.html", booking=None, error="Missing booking_id.")

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
        return render_or_json("public/book_success.html", booking=None, error="Booking not found.")

    return render_or_json("public/book_success.html", booking=booking, error=None)
@public_bp.get("/find-booking")
def find_booking_page():
    return render_or_json("public/find_booking.html", contact="", error=None)
@public_bp.post("/find-booking")
def find_booking_results():
    contact = request.form.get("contact")
    phone, email = _normalize_contact(contact)

    if not phone and not email:
        return render_or_json(
            "public/find_booking.html",
            contact="",
            error="Please enter a phone number or email.",
        )

    bookings = _find_bookings_by_contact(phone, email)
    return render_or_json(
        "public/find_booking_results.html",
        contact=contact.strip(),
        bookings=bookings,
        error=None,
    )
@public_bp.post("/booking/<int:booking_id>/cancel")
def cancel_booking(booking_id: int):
    contact = request.form.get("contact")
    booking_code = (request.form.get("booking_code") or "").strip()

    phone, email = _normalize_contact(contact)

    if not booking_code or (not phone and not email):
        # re-render results with error
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

    matches_contact = (
        (phone and booking["customer_phone"] == phone)
        or (email and (booking["customer_email"] or "").lower() == email)
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

    # Mark cancelled (don’t delete)
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

