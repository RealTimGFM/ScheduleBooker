from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta

from flask import jsonify, redirect, render_template, request, session, url_for
from jinja2 import TemplateNotFound
from werkzeug.security import check_password_hash

from ..sqlite_db import execute_db, query_db
from . import admin_bp


def render_or_json(template_name: str, **ctx):
    try:
        return render_template(template_name, **ctx)
    except TemplateNotFound:
        return jsonify({"template": template_name, "context": ctx})


def require_admin():
    return session.get("admin_user_id") is not None


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse_date(date_str: str | None) -> date:
    try:
        return date.fromisoformat(date_str) if date_str else datetime.now().date()
    except ValueError:
        return datetime.now().date()


def _parse_time_hhmm(t: str | None) -> time | None:
    if not t:
        return None
    try:
        tt = time.fromisoformat(t)  # HH:MM
        return time(tt.hour, tt.minute)
    except ValueError:
        return None


@admin_bp.get("/login")
def login():
    return render_or_json("admin/login.html", error=None)


@admin_bp.post("/login")
def login_post():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    row = query_db(
        "SELECT id, password_hash FROM admin_users WHERE username = ?",
        (username,),
        one=True,
    )

    if not row or not check_password_hash(row["password_hash"], password):
        return render_or_json("admin/login.html", error="Invalid username/password")

    session["admin_user_id"] = row["id"]
    return redirect(url_for("admin.day"))


@admin_bp.get("/day")
def day():
    if not require_admin():
        return redirect(url_for("admin.login"))

    date_str = request.args.get("date")
    day = _parse_date(date_str)

    day_start = datetime.combine(day, time(0, 0))
    day_end = day_start + timedelta(days=1)

    rows = query_db(
        "SELECT a.*, s.name AS service_name, b.name AS barber_name "
        "FROM appointments a "
        "LEFT JOIN services s ON s.id = a.service_id "
        "LEFT JOIN barbers b ON b.id = a.barber_id "
        "WHERE a.start_time >= ? AND a.start_time < ? "
        "ORDER BY a.start_time ASC",
        (_iso(day_start), _iso(day_end)),
    )
    bookings = [dict(r) for r in rows]

    return render_or_json(
        "admin/day.html",
        date=day.isoformat(),
        bookings=bookings,
        error=None,
    )


@admin_bp.post("/book")
def create_booking():
    if not require_admin():
        return redirect(url_for("admin.login"))

    customer_name = (request.form.get("customer_name") or "").strip()
    customer_phone = (request.form.get("customer_phone") or "").strip() or None
    customer_email = (request.form.get("customer_email") or "").strip().lower() or None

    service_id = request.form.get("service_id", type=int)
    barber_id = request.form.get("barber_id", type=int)  # optional (can be None)
    date_str = request.form.get("date")
    time_str = request.form.get("time")

    if not customer_name or not service_id or not date_str or not time_str:
        # send them back to the day view they were on (best effort)
        return redirect(url_for("admin.day", date=date_str))

    day = _parse_date(date_str)
    t = _parse_time_hhmm(time_str)
    if not t:
        return redirect(url_for("admin.day", date=day.isoformat()))

    start_dt = datetime.combine(day, t)

    # NO VALIDATIONS: compute end_time from service duration (fallback 30)
    svc = query_db("SELECT duration_min FROM services WHERE id = ?", (service_id,), one=True)
    duration_min = int(svc["duration_min"]) if svc and svc["duration_min"] else 30
    end_dt = start_dt + timedelta(minutes=duration_min)

    now = _iso(datetime.now())
    booking_code = secrets.token_urlsafe(8).replace("-", "").replace("_", "")

    execute_db(
        "INSERT INTO appointments "
        "(user_id, barber_id, service_id, customer_name, customer_phone, customer_email, "
        " start_time, end_time, notes, status, booking_code, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            None,
            barber_id,  # may be None
            service_id,
            customer_name,
            customer_phone,
            customer_email,
            _iso(start_dt),
            _iso(end_dt),
            "",  # notes not in admin Day 5 form; keep empty
            "booked",
            booking_code,
            now,
            now,
        ),
    )

    return redirect(url_for("admin.day", date=day.isoformat()))
