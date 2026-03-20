from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..repositories import public_booking_repository as booking_repo

SHOP_CAPACITY_PER_SLOT = 2
SHOP_TIMEZONE = ZoneInfo("America/Toronto")
OPEN = time(11, 0)
CLOSE = time(19, 0)
LAST_END_TIME = time(19, 0)
MAX_BOOKINGS_PER_DAY_MESSAGE = "If you want more than 2 bookings in a day, contact the barber."


def parse_date_or_default(date_str: str | None) -> tuple[str, date] | tuple[None, None]:
    if not date_str:
        d = datetime.now(SHOP_TIMEZONE).date()
        return d.isoformat(), d
    try:
        d = date.fromisoformat(date_str)
        return date_str, d
    except ValueError:
        return None, None


def parse_time_hhmm(time_str: str | None) -> time | None:
    if not time_str:
        return None
    try:
        t = time.fromisoformat(time_str)
        return time(t.hour, t.minute)
    except ValueError:
        return None


def iso_datetime(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(timespec="seconds")


def floor_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


def slot_segments_30min(
    day: date, start_dt: datetime, end_dt: datetime
) -> list[tuple[datetime, datetime]]:
    segments: list[tuple[datetime, datetime]] = []
    cursor = datetime.combine(day, OPEN)
    end = datetime.combine(day, LAST_END_TIME)

    while cursor < end:
        seg_start = cursor
        seg_end = cursor + timedelta(minutes=30)
        if overlaps(seg_start, seg_end, start_dt, end_dt):
            segments.append((seg_start, seg_end))
        cursor += timedelta(minutes=30)

    return segments


def normalize_phone(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def normalize_email(email: str | None) -> str | None:
    e = (email or "").strip().lower()
    return e or None


def normalize_contact(contact: str | None) -> tuple[str | None, str | None]:
    c = (contact or "").strip()
    if not c:
        return None, None
    if "@" in c:
        return None, c.lower()
    digits = "".join(ch for ch in c if ch.isdigit())
    return (digits or None), None


def split_services_by_popularity() -> tuple[list[dict], list[dict]]:
    services = booking_repo.list_active_services()
    most = [service for service in services if service.get("is_popular") == 1]
    other = [service for service in services if service.get("is_popular") != 1]
    return most, other


def load_bookings_for_day(day: date) -> list[dict]:
    day_start = datetime.combine(day, time(0, 0))
    day_end = day_start + timedelta(days=1)
    return booking_repo.list_bookings_for_day(
        iso_datetime(day_start),
        iso_datetime(day_end),
    )


def validate_shop_hours_and_past(day: date, start_t: time, end_t: time) -> str | None:
    if day.weekday() == 0:
        return "Shop is closed on Monday."

    now = floor_to_minute(datetime.now(SHOP_TIMEZONE))
    booking_datetime = floor_to_minute(datetime.combine(day, start_t, tzinfo=SHOP_TIMEZONE))

    if booking_datetime < now:
        return "Cannot book in the past."

    if start_t < OPEN or start_t >= CLOSE:
        return f"Start time must be between {OPEN.strftime('%H:%M')} and {CLOSE.strftime('%H:%M')}."

    if end_t > LAST_END_TIME:
        return (
            f"Booking ends at {end_t.strftime('%H:%M')}, but last appointment must end by "
            f"{LAST_END_TIME.strftime('%H:%M')}."
        )

    return None


def _booking_end(booking: dict, service_duration_lookup: dict[int, int]) -> datetime | None:
    try:
        start_dt = datetime.fromisoformat(booking["start_time"])
    except Exception:
        return None

    if booking.get("end_time"):
        try:
            return datetime.fromisoformat(booking["end_time"])
        except Exception:
            pass

    return start_dt + timedelta(minutes=service_duration_lookup.get(booking.get("service_id"), 30))


def build_time_slots(
    day: date, duration_min: int, barbers: list[dict], selected_barber_id: int | None
) -> list[dict]:
    if day.weekday() == 0:
        slots = []
        current = datetime.combine(day, OPEN)
        end = datetime.combine(day, CLOSE)
        while current < end:
            slots.append(
                {
                    "time": current.strftime("%H:%M"),
                    "is_available": False,
                    "reason": "Closed (Monday)",
                }
            )
            current += timedelta(minutes=30)
        return slots

    active_barber_ids = [barber["id"] for barber in barbers]
    if selected_barber_id is not None and selected_barber_id not in active_barber_ids:
        return [{"time": "11:00", "is_available": False, "reason": "Invalid barber"}]

    bookings = load_bookings_for_day(day)
    service_duration_lookup = booking_repo.get_service_duration_lookup()
    parsed = []
    for booking in bookings:
        try:
            start_dt = datetime.fromisoformat(booking["start_time"])
        except Exception:
            continue

        end_dt = _booking_end(booking, service_duration_lookup)
        if end_dt is None:
            continue

        parsed.append({"barber_id": booking.get("barber_id"), "start": start_dt, "end": end_dt})

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
        slot_datetime = slot_start.replace(tzinfo=SHOP_TIMEZONE).replace(second=0, microsecond=0)

        if slot_datetime < now:
            slots.append(
                {"time": slot_start.strftime("%H:%M"), "is_available": False, "reason": "Past"}
            )
            cursor += timedelta(minutes=30)
            continue

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

        is_full = False
        for seg_start, seg_end in slot_segments_30min(day, slot_start, slot_end):
            seg_count = 0
            for parsed_booking in parsed:
                if overlaps(parsed_booking["start"], parsed_booking["end"], seg_start, seg_end):
                    seg_count += 1
            if seg_count >= effective_shop_cap:
                is_full = True
                break

        if is_full:
            slots.append(
                {"time": slot_start.strftime("%H:%M"), "is_available": False, "reason": "Full"}
            )
            cursor += timedelta(minutes=30)
            continue

        def barber_free(barber_id: int) -> bool:
            for parsed_booking in parsed:
                if parsed_booking["barber_id"] == barber_id and overlaps(
                    parsed_booking["start"], parsed_booking["end"], slot_start, slot_end
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
            ok_any = any(barber_free(barber_id) for barber_id in active_barber_ids)
            slots.append(
                {
                    "time": slot_start.strftime("%H:%M"),
                    "is_available": ok_any,
                    "reason": None if ok_any else "Booked",
                }
            )

        cursor += timedelta(minutes=30)

    return slots


def validate_public_booking(
    *,
    service: dict,
    barber: dict | None,
    day: date,
    start_t: time,
    user_id: int | None,
    booking_id: int | None = None,
):
    duration_min = int(service.get("duration_min") or 30)
    start_dt = datetime.combine(day, start_t)
    end_dt = start_dt + timedelta(minutes=duration_min)

    hours_error = validate_shop_hours_and_past(day, start_t, end_dt.time())
    if hours_error:
        return None, None, hours_error

    existing = load_bookings_for_day(day)
    service_duration_lookup = booking_repo.get_service_duration_lookup()

    if user_id:
        user_bookings_today = [
            booking
            for booking in existing
            if booking.get("user_id") == user_id and (not booking_id or booking["id"] != booking_id)
        ]

        if len(user_bookings_today) >= 2:
            return None, None, MAX_BOOKINGS_PER_DAY_MESSAGE

        for booking in user_bookings_today:
            try:
                booking_start = datetime.fromisoformat(booking["start_time"])
            except Exception:
                continue

            booking_end = _booking_end(booking, service_duration_lookup)
            if booking_end is None:
                continue

            if overlaps(booking_start, booking_end, start_dt, end_dt):
                return (
                    None,
                    None,
                    "You already have an appointment at this time. Cannot double-book.",
                )

    if barber is not None:
        for booking in existing:
            if booking_id and booking["id"] == booking_id:
                continue
            if booking.get("barber_id") != barber["id"]:
                continue

            try:
                booking_start = datetime.fromisoformat(booking["start_time"])
            except Exception:
                continue

            booking_end = _booking_end(booking, service_duration_lookup)
            if booking_end is None:
                continue

            if overlaps(booking_start, booking_end, start_dt, end_dt):
                return None, None, "That time is no longer available. Please choose another slot."

    for seg_start, seg_end in slot_segments_30min(day, start_dt, end_dt):
        concurrent_count = 0
        for booking in existing:
            if booking_id and booking["id"] == booking_id:
                continue

            try:
                booking_start = datetime.fromisoformat(booking["start_time"])
            except Exception:
                continue

            booking_end = _booking_end(booking, service_duration_lookup)
            if booking_end is None:
                continue

            if overlaps(booking_start, booking_end, seg_start, seg_end):
                concurrent_count += 1

        if concurrent_count >= SHOP_CAPACITY_PER_SLOT:
            return None, None, "This time slot is fully booked. Please pick another time."

    return start_dt, end_dt, None


def validate_customer_portal_booking(
    *,
    day: date,
    start_t: time,
    duration_min: int,
    user_id: int,
    booking_id: int | None = None,
):
    start_dt = datetime.combine(day, start_t)
    end_dt = start_dt + timedelta(minutes=duration_min)

    hours_error = validate_shop_hours_and_past(day, start_t, end_dt.time())
    if hours_error:
        return None, None, hours_error

    existing = load_bookings_for_day(day)
    service_duration_lookup = booking_repo.get_service_duration_lookup()

    user_bookings_today = [
        booking
        for booking in existing
        if booking.get("user_id") == user_id and (not booking_id or booking["id"] != booking_id)
    ]
    if len(user_bookings_today) >= 2:
        return None, None, MAX_BOOKINGS_PER_DAY_MESSAGE

    for booking in user_bookings_today:
        try:
            booking_start = datetime.fromisoformat(booking["start_time"])
        except Exception:
            continue

        booking_end = _booking_end(booking, service_duration_lookup)
        if booking_end is None:
            continue

        if overlaps(booking_start, booking_end, start_dt, end_dt):
            return None, None, "You already have an appointment at this time. Cannot double-book."

    for seg_start, seg_end in slot_segments_30min(day, start_dt, end_dt):
        concurrent_count = 0
        for booking in existing:
            if booking_id and booking["id"] == booking_id:
                continue

            try:
                booking_start = datetime.fromisoformat(booking["start_time"])
            except Exception:
                continue

            booking_end = _booking_end(booking, service_duration_lookup)
            if booking_end is None:
                continue

            if overlaps(booking_start, booking_end, seg_start, seg_end):
                concurrent_count += 1

        if concurrent_count >= SHOP_CAPACITY_PER_SLOT:
            return None, None, "This time slot is fully booked. Please pick another time."

    return start_dt, end_dt, None


def count_bookings_for_contact(day: date, phone: str | None, email: str | None) -> int:
    day_start = datetime.combine(day, time(0, 0))
    day_end = day_start + timedelta(days=1)
    return booking_repo.count_bookings_for_contact_on_day(
        day_start_iso=iso_datetime(day_start),
        day_end_iso=iso_datetime(day_end),
        phone=normalize_phone(phone) if phone else "",
        email=normalize_email(email),
    )


def get_booking_start_in_shop_timezone(start_time_raw: str) -> datetime:
    start_dt = datetime.fromisoformat(start_time_raw)

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=SHOP_TIMEZONE)
    else:
        start_dt = start_dt.astimezone(SHOP_TIMEZONE)

    return floor_to_minute(start_dt)


def validate_customer_cancellation_window(booking) -> str | None:
    try:
        booking_start = get_booking_start_in_shop_timezone(booking["start_time"])
    except Exception:
        return "Invalid booking date/time."

    now = floor_to_minute(datetime.now(SHOP_TIMEZONE))

    if booking_start < now:
        return "Cannot cancel past bookings."

    time_until_start = (booking_start - now).total_seconds() / 60
    if time_until_start < 30:
        return "Cannot cancel within 30 minutes of start time."

    return None


def store_cancellation_and_mark_cancelled(booking, cancelled_by: str) -> None:
    cancelled_at = iso_datetime(datetime.now())
    booking_repo.insert_cancellation(
        booking_id=booking["id"],
        customer_name=booking["customer_name"],
        customer_phone=booking["customer_phone"],
        customer_email=booking["customer_email"],
        barber_id=booking["barber_id"],
        barber_name=booking["barber_name"],
        service_id=booking["service_id"],
        service_name=booking["service_name"],
        start_datetime=booking["start_time"],
        end_datetime=booking["end_time"],
        cancelled_at=cancelled_at,
        cancelled_by=cancelled_by,
    )
    booking_repo.mark_appointment_cancelled(booking["id"], updated_at=cancelled_at)


def generate_booking_code() -> str:
    for _ in range(5):
        code = secrets.token_urlsafe(8).replace("-", "").replace("_", "")
        if not booking_repo.is_booking_code_taken(code):
            return code
    return secrets.token_urlsafe(12).replace("-", "").replace("_", "")
