import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from werkzeug.security import generate_password_hash

from schedulebooker import create_app
from schedulebooker.sqlite_db import get_db
from schedulebooker.admin import routes as admin_routes


def _extract_csrf(html: str) -> str:
    # meta tag (recommended)
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if m:
        return m.group(1)

    # hidden input fallback
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if m:
        return m.group(1)

    raise AssertionError("Could not find CSRF token in HTML response.")


@pytest.fixture()
def app(tmp_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "test.db"),
        SECRET_KEY="test-secret-key",  # stable for tests
    )

    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql") as f:
            db.executescript(f.read().decode("utf-8"))

        # seed one admin user (if your login route uses it)
        db.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            ("T", generate_password_hash("1")),
        )
        db.commit()

    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def _login_as_admin(client):
    # bypass login route: set the exact session keys your require_admin() expects
    with client.session_transaction() as s:
        s["admin_user_id"] = 1
        s[admin_routes._ADMIN_EPOCH_KEY] = admin_routes._ADMIN_EPOCH
        s[admin_routes._ADMIN_LAST_SEEN_KEY] = int(time.time())


def _insert_future_booking(app, phone="5551112222"):
    tz = ZoneInfo("America/Toronto")
    start = (datetime.now(tz) + timedelta(hours=2)).replace(tzinfo=None)
    start_iso = start.isoformat(timespec="seconds")

    with app.app_context():
        db = get_db()
        cur = db.execute(
            """
            INSERT INTO appointments (customer_name, customer_phone, start_time, end_time, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'booked', datetime('now'), datetime('now'))
            """,
            ("Test User", phone, start_iso, None),
        )
        db.commit()
        return cur.lastrowid


def test_admin_delete_requires_csrf(client, app):
    _login_as_admin(client)
    booking_id = _insert_future_booking(app)

    resp = client.post(f"/admin/book/{booking_id}/delete")
    assert resp.status_code == 400  # CSRF missing


def test_admin_delete_with_csrf_succeeds(client, app):
    _login_as_admin(client)
    booking_id = _insert_future_booking(app)

    page = client.get("/admin/day")
    token = _extract_csrf(page.get_data(as_text=True))

    resp = client.post(f"/admin/book/{booking_id}/delete", data={"csrf_token": token})
    assert resp.status_code in (302, 303)

    # verify it is gone
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT id FROM appointments WHERE id = ?", (booking_id,)).fetchone()
        assert row is None


def test_public_cancel_api_requires_csrf(client, app):
    booking_id = _insert_future_booking(app, phone="5551112222")

    resp = client.post(f"/api/booking/{booking_id}/cancel", json={"phone": "5551112222"})
    assert resp.status_code == 400  # CSRF missing


def test_public_cancel_api_with_csrf_succeeds(client, app):
    booking_id = _insert_future_booking(app, phone="5551112222")

    # get csrf token from a public page (admin login is public)
    page = client.get("/admin/login")
    token = _extract_csrf(page.get_data(as_text=True))

    resp = client.post(
        f"/api/booking/{booking_id}/cancel",
        json={"phone": "5551112222"},
        headers={"X-CSRFToken": token},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data and data.get("ok") is True

    # verify booking deleted
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT id FROM appointments WHERE id = ?", (booking_id,)).fetchone()
        assert row is None


def test_csrf_token_is_rendered_in_base_html(client):
    page = client.get("/admin/login")
    html = page.get_data(as_text=True)
    # either meta or hidden input must exist
    assert ("name=\"csrf-token\"" in html) or ("name=\"csrf_token\"" in html)
