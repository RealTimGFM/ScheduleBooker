from __future__ import annotations

from datetime import date, datetime, time, timedelta

from flask import jsonify, redirect, render_template, request, url_for
from jinja2 import TemplateNotFound

from ..sqlite_db import query_db
from . import public_bp


SHOP_CAPACITY_PER_SLOT = 3  # safe default; can be changed later


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
    rows = query_db(
        "SELECT id, name, is_active "
        "FROM barbers WHERE is_active = 1 "
        "ORDER BY name ASC"
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
        "SELECT id, barber_id, service_id, start_time, end_time, status "
        "FROM appointments "
        "WHERE status != 'cancelled' AND start_time >= ? AND start_time < ?",
        (_iso(day_start), _iso(day_end)),
    )
    return [dict(r) for r in rows]


def _build_time_slots(day: date, duration_min: int, barbers: list[dict], selected_barber_id: int | None):
    # Monday closed (weekday: Mon=0)
    OPEN = time(11, 0)
    CLOSE = time(19, 0)

    if day.weekday() == 0:
        # still produce the grid so UI can show it greyed out
        slots = []
        t = datetime.combine(day, OPEN)
        end = datetime.combine(day, CLOSE)
        while t < end:
            slots.append({"time": t.strftime("%H:%M"), "is_available": False, "reason": "Closed (Monday)"})
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
    effective_shop_cap = min(SHOP_CAPACITY_PER_SLOT, len(active_barber_ids)) if active_barber_ids else 0

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
            slots.append({"time": slot_start.strftime("%H:%M"), "is_available": False, "reason": "No barbers"})
            cursor += timedelta(minutes=30)
            continue

        if shop_overlaps >= effective_shop_cap:
            slots.append({"time": slot_start.strftime("%H:%M"), "is_available": False, "reason": "Full"})
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
            slots.append({"time": slot_start.strftime("%H:%M"), "is_available": ok, "reason": None if ok else "Booked"})
        else:
            ok_any = any(barber_free(bid) for bid in active_barber_ids)
            slots.append({"time": slot_start.strftime("%H:%M"), "is_available": ok_any, "reason": None if ok_any else "Booked"})

        cursor += timedelta(minutes=30)

    return slots


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
