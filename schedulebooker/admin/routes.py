from __future__ import annotations

import secrets
import time as pytime
from datetime import date, datetime, time, timedelta

from flask import jsonify, redirect, render_template, request, session, url_for
from jinja2 import TemplateNotFound
from werkzeug.security import check_password_hash

from ..sqlite_db import execute_db, query_db
from . import admin_bp

DAY_START_HOUR = 9
DAY_END_HOUR = 19  # inclusive label (19:00)

# Admin security / UX
ADMIN_IDLE_TIMEOUT_SEC = 15 * 60  # 15 minutes
_ADMIN_EPOCH = secrets.token_urlsafe(
    12
)  # changes every app start (forces admin logged out on restart)

_ADMIN_EPOCH_KEY = "_admin_epoch"
_ADMIN_LAST_SEEN_KEY = "_admin_last_seen"


def render_or_json(template_name: str, **ctx):
    try:
        return render_template(template_name, **ctx)
    except TemplateNotFound:
        return jsonify({"template": template_name, "context": ctx})


def _clear_admin_session():
    session.pop("admin_user_id", None)
    session.pop(_ADMIN_EPOCH_KEY, None)
    session.pop(_ADMIN_LAST_SEEN_KEY, None)


@admin_bp.before_app_request
def _admin_session_housekeeping():
    """
    1) Force admin to be logged out when the app starts (epoch mismatch after restart).
    2) Auto logout after 15 minutes of inactivity (based on last admin activity).
    3) Do NOT extend admin session while browsing public pages; only extend on /admin routes.
    """
    if "admin_user_id" not in session:
        return

    # If app restarted, invalidate any old admin cookies immediately (so navbar won't show "Admin logout")
    if session.get(_ADMIN_EPOCH_KEY) != _ADMIN_EPOCH:
        _clear_admin_session()
        return

    now = int(pytime.time())
    last_seen = session.get(_ADMIN_LAST_SEEN_KEY)

    if last_seen is not None:
        try:
            last_seen = int(last_seen)
        except (TypeError, ValueError):
            last_seen = None

    # Expire if idle too long
    if last_seen is not None and (now - last_seen) > ADMIN_IDLE_TIMEOUT_SEC:
        _clear_admin_session()
        return

    # Only "keep alive" when actively using admin pages
    if request.path.startswith("/admin"):
        session[_ADMIN_LAST_SEEN_KEY] = now


def require_admin() -> bool:
    # Housekeeping already runs before requests, but keep this defensive.
    if session.get("admin_user_id") is None:
        return False
    if session.get(_ADMIN_EPOCH_KEY) != _ADMIN_EPOCH:
        _clear_admin_session()
        return False
    return True


def _parse_date(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        return None


def _parse_time_hhmm(t: str | None) -> time | None:
    if not t:
        return None
    try:
        tt = time.fromisoformat(t)  # HH:MM
        return time(tt.hour, tt.minute)
    except ValueError:
        return None


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_end_exclusive(d: date) -> date:
    start = _month_start(d)
    if start.month == 12:
        return date(start.year + 1, 1, 1)
    return date(start.year, start.month + 1, 1)


def _week_start_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday=0


@admin_bp.get("/")
def home():
    """Navbar entry point: if not logged in, go to admin login; else go to admin calendar."""
    if require_admin():
        return redirect(url_for("admin.day"))
    return redirect(url_for("admin.login"))


@admin_bp.get("/logout")
def logout():
    _clear_admin_session()
    return redirect(url_for("public.services"))


@admin_bp.get("/login")
def login():
    return render_or_json("admin/login.html", error=None)


@admin_bp.post("/login")
def login_post():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    row = query_db("SELECT * FROM admin_users WHERE username = ?", (username,), one=True)
    if not row or not check_password_hash(row["password_hash"], password):
        return render_or_json("admin/login.html", error="Invalid username/password")

    # Admin session starts here
    session["admin_user_id"] = row["id"]
    session[_ADMIN_EPOCH_KEY] = _ADMIN_EPOCH
    session[_ADMIN_LAST_SEEN_KEY] = int(pytime.time())

    next_url = (request.form.get("next") or "").strip()
    if next_url.startswith("/"):
        return redirect(next_url)

    return redirect(url_for("admin.day"))


@admin_bp.get("/day")
def day():
    if not require_admin():
        return redirect(url_for("admin.login", next=request.full_path))

    date_str = request.args.get("date")
    selected_day = _parse_date(date_str) or date.today()

    # Day bookings
    start = datetime.combine(selected_day, time(0, 0))
    end = start + timedelta(days=1)

    bookings = query_db(
        """
        SELECT a.*,
               s.name AS service_name,
               b.name AS barber_name
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN barbers  b ON a.barber_id = b.id
        WHERE a.start_time >= ? AND a.start_time < ?
        ORDER BY a.start_time
        """,
        (_iso(start), _iso(end)),
    )

    services = query_db("SELECT id, name, duration_min, price FROM services ORDER BY id ASC")
    barbers = query_db("SELECT id, name FROM barbers WHERE is_active = 1 ORDER BY name ASC")

    wk_start = _week_start_monday(selected_day)
    wk_end = wk_start + timedelta(days=7)

    week_rows = query_db(
        """
        SELECT a.*,
               s.name AS service_name,
               b.name AS barber_name
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN barbers  b ON a.barber_id = b.id
        WHERE a.start_time >= ? AND a.start_time < ?
        ORDER BY a.start_time
        """,
        (
            _iso(datetime.combine(wk_start, time(0, 0))),
            _iso(datetime.combine(wk_end, time(0, 0))),
        ),
    )

    week_map: dict[str, list[dict]] = {}
    for r in week_rows:
        key = (r["start_time"] or "")[:10]
        week_map.setdefault(key, []).append(dict(r))

    week_days = []
    for i in range(7):
        d = wk_start + timedelta(days=i)
        iso = d.isoformat()
        week_days.append(
            {
                "date": iso,
                "label": d.strftime("%a %m/%d"),
                "bookings": week_map.get(iso, []),
            }
        )

    m_start = _month_start(selected_day)
    m_end = _month_end_exclusive(selected_day)

    month_counts_rows = query_db(
        """
        SELECT substr(start_time, 1, 10) AS d, COUNT(*) AS cnt
        FROM appointments
        WHERE start_time >= ? AND start_time < ?
        GROUP BY d
        """,
        (
            _iso(datetime.combine(m_start, time(0, 0))),
            _iso(datetime.combine(m_end, time(0, 0))),
        ),
    )
    month_counts = {r["d"]: int(r["cnt"]) for r in month_counts_rows}

    cells = []
    for _ in range(m_start.weekday()):
        cells.append(None)

    days_in_month = (m_end - m_start).days
    today_iso = date.today().isoformat()
    selected_iso = selected_day.isoformat()

    for i in range(days_in_month):
        d = m_start + timedelta(days=i)
        iso = d.isoformat()
        cells.append(
            {
                "date": iso,
                "day": d.day,
                "count": month_counts.get(iso, 0),
                "is_today": iso == today_iso,
                "is_selected": iso == selected_iso,
            }
        )

    while len(cells) % 7 != 0:
        cells.append(None)

    month_label = m_start.strftime("%B %Y")
    day_hours = list(range(DAY_START_HOUR, DAY_END_HOUR + 1))

    return render_or_json(
        "admin/day.html",
        date=selected_day.isoformat(),
        bookings=[dict(r) for r in bookings],
        services=[dict(r) for r in services],
        barbers=[dict(r) for r in barbers],
        week_days=week_days,
        month_cells=cells,
        month_label=month_label,
        day_hours=day_hours,
        day_start_hour=DAY_START_HOUR,
        error=None,
    )


@admin_bp.post("/book")
def create_booking():
    if not require_admin():
        return redirect(url_for("admin.login", next=request.referrer or url_for("admin.day")))

    customer_name = (request.form.get("customer_name") or "").strip()
    customer_phone = (request.form.get("customer_phone") or "").strip()
    customer_email = (request.form.get("customer_email") or "").strip()

    service_id = request.form.get("service_id", type=int)
    barber_id = request.form.get("barber_id", type=int)

    d = _parse_date(request.form.get("date"))
    t = _parse_time_hhmm(request.form.get("time"))

    if not (customer_name and service_id and d and t):
        return redirect(url_for("admin.day", date=(d or date.today()).isoformat()))

    start_dt = datetime.combine(d, t)

    service = query_db("SELECT * FROM services WHERE id = ?", (service_id,), one=True)
    duration_min = int(service["duration_min"]) if service else 30
    end_dt = start_dt + timedelta(minutes=duration_min)

    booking_code = secrets.token_urlsafe(6)

    execute_db(
        """
        INSERT INTO appointments (
            customer_name, customer_phone, customer_email,
            service_id, barber_id,
            start_time, end_time,
            status, booking_code, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_name,
            customer_phone or None,
            customer_email or None,
            service_id,
            barber_id,
            _iso(start_dt),
            _iso(end_dt),
            "booked",
            booking_code,
            "",
        ),
    )

    return redirect(url_for("admin.day", date=d.isoformat()))


# Add these routes to schedulebooker/admin/routes.py (after create_booking)


@admin_bp.post("/book/<int:booking_id>/edit")
def edit_booking(booking_id: int):
    if not require_admin():
        return redirect(url_for("admin.login", next=request.referrer or url_for("admin.day")))

    booking = query_db("SELECT * FROM appointments WHERE id = ?", (booking_id,), one=True)
    if not booking:
        return redirect(url_for("admin.day"))

    customer_name = (request.form.get("customer_name") or "").strip()
    customer_phone = (request.form.get("customer_phone") or "").strip()
    customer_email = (request.form.get("customer_email") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    service_id = request.form.get("service_id", type=int)
    barber_id = request.form.get("barber_id", type=int)

    d = _parse_date(request.form.get("date"))
    t = _parse_time_hhmm(request.form.get("time"))

    if not (customer_name and service_id and d and t):
        # Redirect back with original date
        return redirect(url_for("admin.day", date=booking["start_time"][:10]))

    start_dt = datetime.combine(d, t)

    service = query_db("SELECT * FROM services WHERE id = ?", (service_id,), one=True)
    duration_min = int(service["duration_min"]) if service else 30
    end_dt = start_dt + timedelta(minutes=duration_min)

    execute_db(
        """
        UPDATE appointments 
        SET customer_name = ?, customer_phone = ?, customer_email = ?,
            service_id = ?, barber_id = ?,
            start_time = ?, end_time = ?,
            notes = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            customer_name,
            customer_phone or None,
            customer_email or None,
            service_id,
            barber_id,
            _iso(start_dt),
            _iso(end_dt),
            notes,
            _iso(datetime.now()),
            booking_id,
        ),
    )

    return redirect(url_for("admin.day", date=d.isoformat()))


@admin_bp.post("/book/<int:booking_id>/delete")
def delete_booking(booking_id: int):
    if not require_admin():
        return redirect(url_for("admin.login", next=request.referrer or url_for("admin.day")))

    booking = query_db("SELECT * FROM appointments WHERE id = ?", (booking_id,), one=True)
    if not booking:
        return redirect(url_for("admin.day"))

    # Soft delete
    execute_db(
        "UPDATE appointments SET status = 'cancelled', updated_at = ? WHERE id = ?",
        (_iso(datetime.now()), booking_id),
    )

    return redirect(url_for("admin.day", date=booking["start_time"][:10]))
