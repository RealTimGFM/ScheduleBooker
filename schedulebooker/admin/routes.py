from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time as pytime
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from ..extensions import csrf, limiter
from flask import app, flash, jsonify, redirect, render_template, request, session, url_for
from jinja2 import TemplateNotFound
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)  # Add generate_password_hash here

from ..sqlite_db import execute_db, query_db
from . import admin_bp

SHOP_TIMEZONE = ZoneInfo("America/Toronto")
OPEN = time(11, 0)
LAST_END_TIME = time(18, 30)

DAY_START_HOUR = 11  # inclusive label (11:00)
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


# =============================================================================
# Admin Settings: Password Reset & Profile Management
# =============================================================================

RESET_TOKEN_EXPIRY_MINUTES = 15
RESET_CODE_LENGTH = 6
RESET_COOLDOWN_SECONDS = 60  # 1 minute between sends
MAX_RESET_ATTEMPTS = 5


def _hash_token(token: str) -> str:
    """Hash a reset token/code for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_reset_code() -> str:
    """Generate a 6-digit numeric code."""
    return "".join(str(secrets.randbelow(10)) for _ in range(RESET_CODE_LENGTH))


def _generate_reset_token() -> str:
    """Generate a secure URL-safe token."""
    return secrets.token_urlsafe(32)


def _send_reset_email(email: str, token: str, admin_username: str) -> dict:
    """
    Prepare email data for EmailJS.
    Returns a dict with email parameters that the frontend will send via EmailJS.

    In production: Frontend calls EmailJS API with this data.
    In dev: We log it to console.
    """

    # Build reset URL (use request context if available, otherwise use config)
    try:
        reset_url = url_for("admin.reset_password", token=token, _external=True)
    except RuntimeError:
        # Fallback if outside request context
        reset_url = f"/admin/reset?token={token}"

    email_data = {
        "to_email": email,
        "to_name": admin_username,
        "subject": "Password Reset Request - ScheduleBooker Admin",
        "message": f"Click the link below to reset your password:\n\n{reset_url}\n\nThis link expires in {RESET_TOKEN_EXPIRY_MINUTES} minutes.\n\nIf you didn't request this, please ignore this email.",
        "reset_url": reset_url,
        "expires_minutes": RESET_TOKEN_EXPIRY_MINUTES,
    }

    # DEV MODE: Log to console
    if app.debug:
        print("\n" + "=" * 60)
        print("PASSWORD RESET EMAIL (EmailJS Data)")
    print("=" * 60)
    print(f"To: {email_data['to_email']}")
    print(f"Subject: {email_data['subject']}")
    print(f"Reset URL: {email_data['reset_url']}")
    print(f"Expires in: {email_data['expires_minutes']} minutes")
    print("=" * 60 + "\n")

    return email_data


def _send_reset_sms(phone: str, code: str, admin_username: str) -> dict:
    """
    Prepare SMS data (we'll send as email since we're not using Twilio).
    Returns a dict with the code for display or email delivery.

    Alternative: Use an SMS gateway email (e.g., phonenumber@carrier.com)
    """

    sms_data = {
        "phone": phone,
        "code": code,
        "username": admin_username,
        "message": f"Your ScheduleBooker admin password reset code is: {code}\n\nThis code expires in {RESET_TOKEN_EXPIRY_MINUTES} minutes.",
    }

    # DEV MODE: Log to console
    print("\n" + "=" * 60)
    print("PASSWORD RESET SMS (Code)")
    print("=" * 60)
    print(f"To: {sms_data['phone']}")
    print(f"Username: {sms_data['username']}")
    print(f"Code: {sms_data['code']}")
    print(f"Expires in: {RESET_TOKEN_EXPIRY_MINUTES} minutes")
    print("=" * 60 + "\n")

    return sms_data


def _check_rate_limit(admin_id: int, channel: str) -> tuple[bool, int]:
    """
    Check if admin can send another reset. Returns (can_send, seconds_remaining).
    """
    row = query_db(
        "SELECT last_sent_at FROM admin_reset_rate_limits WHERE admin_user_id = ? AND channel = ?",
        (admin_id, channel),
        one=True,
    )

    if not row:
        return True, 0

    last_sent = datetime.fromisoformat(row["last_sent_at"])
    elapsed = (datetime.now() - last_sent).total_seconds()

    if elapsed < RESET_COOLDOWN_SECONDS:
        return False, int(RESET_COOLDOWN_SECONDS - elapsed)

    return True, 0


def _update_rate_limit(admin_id: int, channel: str):
    """Update the last sent timestamp for rate limiting."""
    now = _iso(datetime.now())

    execute_db(
        "INSERT OR REPLACE INTO admin_reset_rate_limits "
        "(admin_user_id, channel, last_sent_at) VALUES (?, ?, ?)",
        (admin_id, channel, now),
    )


def _validate_shop_hours(day: date, start_t: time, end_t: time) -> str | None:
    """Validate booking is within shop hours. Returns error message or None."""
    # Monday closed
    if day.weekday() == 0:
        return "Shop is closed on Monday."

    # Check if booking is in the past (Montreal timezone)
    now = datetime.now(SHOP_TIMEZONE)
    booking_datetime = datetime.combine(day, start_t, tzinfo=SHOP_TIMEZONE)

    if booking_datetime < now:
        return "Cannot book in the past."

    # Shop hours: start must be >= 11:00 and < 19:00
    if start_t < OPEN or start_t >= time(19, 0):
        return "Start time must be between 11:00 and 19:00."

    # End time must be <= 18:30
    if end_t > LAST_END_TIME:
        return f"Booking ends at {end_t.strftime('%H:%M')}, but last appointment must end by 18:30."

    return None


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
    reset_success = request.args.get("reset") == "success"
    return render_or_json("admin/login.html", error=None, reset_success=reset_success)


@admin_bp.post("/login")
@limiter.limit("5 per 1 minutes")
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

    from urllib.parse import urlparse

    next_url = (request.form.get("next") or "").strip()
    if next_url:
        # Only allow relative paths on same origin
        parsed = urlparse(next_url)
        if not parsed.netloc and parsed.path.startswith("/"):
            return redirect(next_url)

    return redirect(url_for("admin.day"))

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

    # VALIDATION: Check shop hours
    hours_error = _validate_shop_hours(d, t, end_dt.time())
    if hours_error:
        flash(hours_error, "error")
        return redirect(url_for("admin.day", date=d.isoformat()))

    booking_code = secrets.token_urlsafe(6)
    now = _iso(datetime.now())
    execute_db(
        """
    INSERT INTO appointments (
        customer_name, customer_phone, customer_email,
        service_id, barber_id,
        start_time, end_time,
        status, booking_code, notes,
        created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            now,
            now,
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
        return redirect(url_for("admin.day", date=booking["start_time"][:10]))

    start_dt = datetime.combine(d, t)

    service = query_db("SELECT * FROM services WHERE id = ?", (service_id,), one=True)
    duration_min = int(service["duration_min"]) if service else 30
    end_dt = start_dt + timedelta(minutes=duration_min)

    # VALIDATION: Check shop hours
    hours_error = _validate_shop_hours(d, t, end_dt.time())
    if hours_error:
        flash(hours_error, "error")
        return redirect(url_for("admin.day", date=d.isoformat()))

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

    # HARD DELETE (not soft delete)
    execute_db("DELETE FROM appointments WHERE id = ?", (booking_id,))

    return redirect(url_for("admin.day", date=booking["start_time"][:10]))


# =============================================================================
# Admin: Services CRUD (with soft-delete via is_active=0)
# =============================================================================

ALLOWED_SERVICE_CATEGORIES = ("Homme", "Femme", "General")


def _service_error_from_code(code: str | None) -> str | None:
    if not code:
        return None
    mapping = {
        "not_found": "Service not found.",
        "confirm_required": "Confirmation missing. Action cancelled.",
        "duplicate_name": "A service with that name already exists.",
        "invalid_form": "Please correct the highlighted fields.",
    }
    return mapping.get(code, "Something went wrong.")


def _parse_service_form(form) -> tuple[dict, str | None]:
    """
    Returns: (data, error_message)
    """
    name = (form.get("name") or "").strip()
    category = (form.get("category") or "General").strip()
    if category not in ALLOWED_SERVICE_CATEGORIES:
        category = "General"

    # numbers
    try:
        duration_min = int(form.get("duration_min") or 30)
    except ValueError:
        duration_min = -1

    try:
        price = float(form.get("price") or 0)
    except ValueError:
        price = -1

    try:
        sort_order = int(form.get("sort_order") or 0)
    except ValueError:
        sort_order = 0

    # checkboxes
    price_is_from = 1 if form.get("price_is_from") else 0
    is_active = 1 if form.get("is_active") else 0
    is_popular = 1 if form.get("is_popular") else 0

    price_label = (form.get("price_label") or "").strip()

    # basic validation
    if not name:
        return {}, "Name is required."
    if duration_min <= 0:
        return {}, "Duration must be a positive number."
    if price < 0:
        return {}, "Price must be 0 or more."

    data = {
        "name": name,
        "category": category,
        "duration_min": duration_min,
        "price": price,
        "price_is_from": price_is_from,
        "price_label": price_label,
        "is_active": is_active,
        "is_popular": is_popular,
        "sort_order": sort_order,
    }
    return data, None


@admin_bp.get("/services")
def services_list():
    if not require_admin():
        return redirect(url_for("admin.login", next=request.full_path))

    # "Hidden by default": show active services prominently, hidden services collapsed.
    active = query_db(
        """
        SELECT *
        FROM services
        WHERE is_active = 1
        ORDER BY sort_order ASC, name ASC
        """
    )
    hidden = query_db(
        """
        SELECT *
        FROM services
        WHERE is_active = 0
        ORDER BY sort_order ASC, name ASC
        """
    )

    error = _service_error_from_code(request.args.get("error"))
    return render_or_json(
        "admin/services.html",
        active_services=active,
        hidden_services=hidden,
        error=error,
    )


@admin_bp.route("/services/new", methods=["GET", "POST"])
def services_new():
    if not require_admin():
        return redirect(url_for("admin.login", next=request.full_path))

    if request.method == "POST":
        data, err = _parse_service_form(request.form)
        if err:
            return render_or_json(
                "admin/service_form.html",
                mode="create",
                service=data,
                error=err,
                categories=ALLOWED_SERVICE_CATEGORIES,
            )

        try:
            execute_db(
                """
                INSERT INTO services
                  (name, category, duration_min, price, price_is_from, price_label,
                   is_active, is_popular, sort_order)
                VALUES
                  (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["name"],
                    data["category"],
                    data["duration_min"],
                    data["price"],
                    data["price_is_from"],
                    data["price_label"],
                    data["is_active"],
                    data["is_popular"],
                    data["sort_order"],
                ),
            )
        except sqlite3.IntegrityError:
            return redirect(url_for("admin.services_list", error="duplicate_name"))

        return redirect(url_for("admin.services_list"))

    # GET defaults
    service = {
        "name": "",
        "category": "General",
        "duration_min": 30,
        "price": 0,
        "price_is_from": 0,
        "price_label": "",
        "is_active": 1,
        "is_popular": 0,
        "sort_order": 0,
    }
    return render_or_json(
        "admin/service_form.html",
        mode="create",
        service=service,
        categories=ALLOWED_SERVICE_CATEGORIES,
        error=None,
    )


@admin_bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
def services_edit(service_id: int):
    if not require_admin():
        return redirect(url_for("admin.login", next=request.full_path))

    svc = query_db("SELECT * FROM services WHERE id = ?", (service_id,), one=True)
    if not svc:
        return redirect(url_for("admin.services_list", error="not_found"))

    if request.method == "POST":
        data, err = _parse_service_form(request.form)
        if err:
            # keep id so the form can post correctly
            data["id"] = service_id
            return render_or_json(
                "admin/service_form.html",
                mode="edit",
                service=data,
                categories=ALLOWED_SERVICE_CATEGORIES,
                error=err,
            )

        try:
            execute_db(
                """
                UPDATE services
                SET name=?,
                    category=?,
                    duration_min=?,
                    price=?,
                    price_is_from=?,
                    price_label=?,
                    is_active=?,
                    is_popular=?,
                    sort_order=?
                WHERE id=?
                """,
                (
                    data["name"],
                    data["category"],
                    data["duration_min"],
                    data["price"],
                    data["price_is_from"],
                    data["price_label"],
                    data["is_active"],
                    data["is_popular"],
                    data["sort_order"],
                    service_id,
                ),
            )
        except sqlite3.IntegrityError:
            return redirect(url_for("admin.services_list", error="duplicate_name"))

        return redirect(url_for("admin.services_list"))

    # GET
    return render_or_json(
        "admin/service_form.html",
        mode="edit",
        service=svc,
        categories=ALLOWED_SERVICE_CATEGORIES,
        error=None,
    )


@admin_bp.post("/services/<int:service_id>/hide")
def services_hide(service_id: int):
    if not require_admin():
        return redirect(
            url_for("admin.login", next=request.referrer or url_for("admin.services_list"))
        )

    # soft delete = hide
    execute_db("UPDATE services SET is_active = 0 WHERE id = ?", (service_id,))
    return redirect(url_for("admin.services_list"))


@admin_bp.post("/services/<int:service_id>/restore")
def services_restore(service_id: int):
    if not require_admin():
        return redirect(
            url_for("admin.login", next=request.referrer or url_for("admin.services_list"))
        )

    execute_db("UPDATE services SET is_active = 1 WHERE id = ?", (service_id,))
    return redirect(url_for("admin.services_list"))


# =============================================================================
# Admin: Barbers CRUD (with soft-delete via is_active=0)
# =============================================================================


def _barber_error_from_code(code: str | None) -> str | None:
    if not code:
        return None
    mapping = {
        "not_found": "Barber not found.",
        "confirm_required": "Confirmation missing. Action cancelled.",
        "duplicate_name": "A barber with that name already exists.",
        "invalid_form": "Please correct the highlighted fields.",
    }
    return mapping.get(code, "Something went wrong.")


def _parse_barber_form(form) -> tuple[dict, str | None]:
    """
    Returns: (data, error_message)
    """
    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()

    # checkboxes
    is_active = 1 if form.get("is_active") else 0

    # validation
    if not name:
        return {}, "Name is required."
    if not phone:
        return {}, "Phone is required."

    data = {
        "name": name,
        "phone": phone,
        "is_active": is_active,
    }
    return data, None


@admin_bp.get("/barbers")
def barbers_list():
    if not require_admin():
        return redirect(url_for("admin.login", next=request.full_path))

    active = query_db("SELECT * FROM barbers WHERE is_active = 1 ORDER BY name ASC")
    hidden = query_db("SELECT * FROM barbers WHERE is_active = 0 ORDER BY name ASC")

    error = _barber_error_from_code(request.args.get("error"))
    return render_or_json(
        "admin/barbers.html",
        active_barbers=active,
        hidden_barbers=hidden,
        error=error,
    )


@admin_bp.route("/barbers/new", methods=["GET", "POST"])
def barbers_new():
    if not require_admin():
        return redirect(url_for("admin.login", next=request.full_path))

    if request.method == "POST":
        data, err = _parse_barber_form(request.form)
        if err:
            return render_or_json(
                "admin/barber_form.html",
                mode="create",
                barber=data,
                error=err,
            )

        try:
            execute_db(
                "INSERT INTO barbers (name, phone, is_active) VALUES (?, ?, ?)",
                (data["name"], data["phone"], data["is_active"]),
            )
        except sqlite3.IntegrityError:
            return redirect(url_for("admin.barbers_list", error="duplicate_name"))

        return redirect(url_for("admin.barbers_list"))

    # GET defaults
    barber = {
        "name": "",
        "phone": "",
        "is_active": 1,
    }
    return render_or_json(
        "admin/barber_form.html",
        mode="create",
        barber=barber,
        error=None,
    )


@admin_bp.route("/barbers/<int:barber_id>/edit", methods=["GET", "POST"])
def barbers_edit(barber_id: int):
    if not require_admin():
        return redirect(url_for("admin.login", next=request.full_path))

    barber = query_db("SELECT * FROM barbers WHERE id = ?", (barber_id,), one=True)
    if not barber:
        return redirect(url_for("admin.barbers_list", error="not_found"))

    if request.method == "POST":
        data, err = _parse_barber_form(request.form)
        if err:
            data["id"] = barber_id
            return render_or_json(
                "admin/barber_form.html",
                mode="edit",
                barber=data,
                error=err,
            )

        try:
            execute_db(
                "UPDATE barbers SET name=?, phone=?, is_active=? WHERE id=?",
                (data["name"], data["phone"], data["is_active"], barber_id),
            )
        except sqlite3.IntegrityError:
            return redirect(url_for("admin.barbers_list", error="duplicate_name"))

        return redirect(url_for("admin.barbers_list"))

    return render_or_json(
        "admin/barber_form.html",
        mode="edit",
        barber=barber,
        error=None,
    )


@admin_bp.post("/barbers/<int:barber_id>/hide")
def barbers_hide(barber_id: int):
    if not require_admin():
        return redirect(
            url_for("admin.login", next=request.referrer or url_for("admin.barbers_list"))
        )

    execute_db("UPDATE barbers SET is_active = 0 WHERE id = ?", (barber_id,))
    return redirect(url_for("admin.barbers_list"))


@admin_bp.post("/barbers/<int:barber_id>/restore")
def barbers_restore(barber_id: int):
    if not require_admin():
        return redirect(
            url_for("admin.login", next=request.referrer or url_for("admin.barbers_list"))
        )

    execute_db("UPDATE barbers SET is_active = 1 WHERE id = ?", (barber_id,))
    return redirect(url_for("admin.barbers_list"))


# =============================================================================
# Admin Settings Routes
# =============================================================================


@admin_bp.get("/settings")
def settings():
    """Admin settings page: profile + password management."""
    if not require_admin():
        return redirect(url_for("admin.login", next=request.full_path))

    admin_id = session.get("admin_user_id")
    admin = query_db(
        "SELECT id, username, email, phone FROM admin_users WHERE id = ?",
        (admin_id,),
        one=True,
    )

    if not admin:
        _clear_admin_session()
        return redirect(url_for("admin.login"))

    return render_or_json("admin/settings.html", admin=dict(admin), error=None, success=None)


@admin_bp.post("/settings/profile")
def update_profile():
    """Update admin profile (username, email, phone)."""
    if not require_admin():
        return redirect(url_for("admin.login", next=url_for("admin.settings")))

    admin_id = session.get("admin_user_id")
    admin = query_db("SELECT * FROM admin_users WHERE id = ?", (admin_id,), one=True)

    if not admin:
        _clear_admin_session()
        return redirect(url_for("admin.login"))

    # Get form data
    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip().lower() or None
    phone = (request.form.get("phone") or "").strip() or None
    current_password = request.form.get("current_password") or ""

    # Validate
    if not username:
        return render_or_json(
            "admin/settings.html",
            admin=dict(admin),
            error="Username is required.",
            success=None,
        )

    # Require current password for security
    if not check_password_hash(admin["password_hash"], current_password):
        return render_or_json(
            "admin/settings.html",
            admin=dict(admin),
            error="Current password is incorrect.",
            success=None,
        )

    # Check username uniqueness (if changed)
    if username != admin["username"]:
        existing = query_db(
            "SELECT id FROM admin_users WHERE username = ? AND id != ?",
            (username, admin_id),
            one=True,
        )
        if existing:
            return render_or_json(
                "admin/settings.html",
                admin=dict(admin),
                error="Username already taken.",
                success=None,
            )

    # Update
    execute_db(
        "UPDATE admin_users SET username = ?, email = ?, phone = ? WHERE id = ?",
        (username, email, phone, admin_id),
    )

    # Fetch updated data
    updated_admin = query_db(
        "SELECT id, username, email, phone FROM admin_users WHERE id = ?",
        (admin_id,),
        one=True,
    )

    return render_or_json(
        "admin/settings.html",
        admin=dict(updated_admin),
        error=None,
        success="Profile updated successfully.",
    )


@admin_bp.post("/settings/password")
def change_password():
    """Change admin password (requires current password)."""
    if not require_admin():
        return redirect(url_for("admin.login", next=url_for("admin.settings")))

    admin_id = session.get("admin_user_id")
    admin = query_db("SELECT * FROM admin_users WHERE id = ?", (admin_id,), one=True)

    if not admin:
        _clear_admin_session()
        return redirect(url_for("admin.login"))

    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    # Validate current password
    if not check_password_hash(admin["password_hash"], current_password):
        return render_or_json(
            "admin/settings.html",
            admin=dict(admin),
            error="Current password is incorrect.",
            success=None,
        )

    # Validate new password
    if len(new_password) < 8:
        return render_or_json(
            "admin/settings.html",
            admin=dict(admin),
            error="New password must be at least 8 characters.",
            success=None,
        )

    if new_password != confirm_password:
        return render_or_json(
            "admin/settings.html",
            admin=dict(admin),
            error="New passwords do not match.",
            success=None,
        )

    # Update password
    new_hash = generate_password_hash(new_password)
    execute_db("UPDATE admin_users SET password_hash = ? WHERE id = ?", (new_hash, admin_id))

    # Fetch fresh admin data
    updated_admin = query_db(
        "SELECT id, username, email, phone FROM admin_users WHERE id = ?",
        (admin_id,),
        one=True,
    )

    return render_or_json(
        "admin/settings.html",
        admin=dict(updated_admin),
        error=None,
        success="Password changed successfully.",
    )


@admin_bp.route("/forgot", methods=["GET", "POST"])
def forgot_password():
    """Forgot password entry point - choose email or SMS."""
    if request.method == "GET":
        return render_or_json("admin/forgot_password.html", error=None, success=None)

    # POST: send reset code/link
    identifier = (request.form.get("identifier") or "").strip().lower()
    channel = request.form.get("channel")  # 'email' or 'sms'

    if not identifier or channel not in ("email", "sms"):
        return render_or_json(
            "admin/forgot_password.html",
            error="Please provide your email or phone and select a reset method.",
            success=None,
        )

    # Find admin by email or phone
    if channel == "email":
        admin = query_db(
            "SELECT * FROM admin_users WHERE LOWER(email) = ?", (identifier,), one=True
        )
    else:  # sms
        admin = query_db("SELECT * FROM admin_users WHERE phone = ?", (identifier,), one=True)

    # Always show success to prevent user enumeration
    if not admin:
        return render_or_json(
            "admin/forgot_password.html",
            error=None,
            success=f"If an account exists, a reset {channel} has been sent.",
        )

    admin_id = admin["id"]
    admin_username = admin["username"]

    # Check rate limit
    can_send, wait_seconds = _check_rate_limit(admin_id, channel)
    if not can_send:
        return render_or_json(
            "admin/forgot_password.html",
            error=f"Please wait {wait_seconds} seconds before requesting another reset.",
            success=None,
        )

    # Generate token/code
    if channel == "email":
        token = _generate_reset_token()
        token_hash = _hash_token(token)
    else:  # sms
        token = _generate_reset_code()
        token_hash = _hash_token(token)

    # Store reset token
    expires_at = _iso(datetime.now() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES))
    execute_db(
        "INSERT INTO admin_password_resets "
        "(admin_user_id, token_hash, channel, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (admin_id, token_hash, channel, expires_at, _iso(datetime.now())),
    )

    # Prepare email/sms data (logged to console in dev)
    if channel == "email":
        _send_reset_email(admin["email"], token, admin_username)
        # email_data = _send_reset_email(admin["email"], token, admin_username)
        # In production with EmailJS, you'd return this data to frontend
        # For now, it's logged to console
    else:
        _send_reset_sms(admin["phone"], token, admin_username)
        # sms_data = _send_reset_sms(admin["phone"], token, admin_username)
        # SMS code is logged to console

    # Update rate limit
    _update_rate_limit(admin_id, channel)

    success_msg = f"Reset {channel} sent! "
    if channel == "email":
        success_msg += "Check your email for the reset link."
    else:
        success_msg += "Check the console/logs for your 6-digit code."

    return render_or_json("admin/forgot_password.html", error=None, success=success_msg)


@admin_bp.route("/reset", methods=["GET", "POST"])
def reset_password():
    """Reset password with token/code."""
    token_from_url = request.args.get("token")  # For email links

    if request.method == "GET":
        return render_or_json(
            "admin/reset_password.html",
            token=token_from_url or "",
            error=None,
            success=None,
        )

    # POST: verify token and set new password
    token_input = (request.form.get("token") or "").strip()
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not token_input:
        return render_or_json(
            "admin/reset_password.html",
            token="",
            error="Reset code/token is required.",
            success=None,
        )

    # Validate new password
    if len(new_password) < 8:
        return render_or_json(
            "admin/reset_password.html",
            token=token_input,
            error="Password must be at least 8 characters.",
            success=None,
        )

    if new_password != confirm_password:
        return render_or_json(
            "admin/reset_password.html",
            token=token_input,
            error="Passwords do not match.",
            success=None,
        )

    # Find reset token
    token_hash = _hash_token(token_input)
    reset = query_db(
        "SELECT * FROM admin_password_resets WHERE token_hash = ? AND used_at IS NULL",
        (token_hash,),
        one=True,
    )

    if not reset:
        return render_or_json(
            "admin/reset_password.html",
            token=token_input,
            error="Invalid or already used reset code/token.",
            success=None,
        )

    # Check expiry
    expires_at = datetime.fromisoformat(reset["expires_at"])
    if datetime.now() > expires_at:
        return render_or_json(
            "admin/reset_password.html",
            token=token_input,
            error="Reset code/token has expired. Please request a new one.",
            success=None,
        )

    # Check attempts
    if reset["attempts"] >= MAX_RESET_ATTEMPTS:
        return render_or_json(
            "admin/reset_password.html",
            token=token_input,
            error="Too many attempts. Please request a new reset code/token.",
            success=None,
        )

    # Increment attempts first
    execute_db(
        "UPDATE admin_password_resets SET attempts = attempts + 1 WHERE id = ?",
        (reset["id"],),
    )

    # Update password
    new_hash = generate_password_hash(new_password)
    execute_db(
        "UPDATE admin_users SET password_hash = ? WHERE id = ?",
        (new_hash, reset["admin_user_id"]),
    )

    # Mark token as used
    execute_db(
        "UPDATE admin_password_resets SET used_at = ? WHERE id = ?",
        (_iso(datetime.now()), reset["id"]),
    )

    return redirect(url_for("admin.login") + "?reset=success")


@admin_bp.get("/api/day-snapshot")
@csrf.exempt  # Requires admin session auth instead
def day_snapshot():
    """API endpoint for polling: returns bookings + cancellations for a date."""
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401

    date_str = request.args.get("date")
    day = _parse_date(date_str)

    if not day:
        # Use shop timezone for "today" (consistent with the rest of your app)
        day = datetime.now(SHOP_TIMEZONE).date()

    # Get bookings
    day_start = datetime.combine(day, time(0, 0))
    day_end = day_start + timedelta(days=1)

    bookings_rows = query_db(
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
        (_iso(day_start), _iso(day_end)),
    )

    # Get cancellations for this day
    cancellations_rows = query_db(
        """
        SELECT id, booking_id, customer_name, customer_phone,
               barber_name, service_name, start_datetime, cancelled_at
        FROM cancellations
        WHERE start_datetime >= ? AND start_datetime < ?
        ORDER BY cancelled_at DESC
        """,
        (_iso(day_start), _iso(day_end)),
    )

    return jsonify(
        {
            "ok": True,
            "date": day.isoformat(),
            "bookings": [dict(r) for r in bookings_rows],
            "cancellations": [dict(r) for r in cancellations_rows],
        }
    )
