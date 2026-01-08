import re
from datetime import datetime, timedelta

import pytest

from schedulebooker import create_app
from schedulebooker.public.routes import SHOP_TIMEZONE
from schedulebooker.sqlite_db import execute_db, get_db, query_db


def _get_csrf(client):
    r = client.get("/services")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    assert m, "CSRF meta tag not found"
    return m.group(1)


@pytest.fixture()
def app(tmp_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "test.db"),
    )

    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql") as f:
            db.executescript(f.read().decode("utf-8"))

        # Seed test data
        db.execute(
            "INSERT INTO services (name, category, duration_min, price, is_active) VALUES (?, ?, ?, ?, ?)",
            ("Test Service", "Homme", 30, 15.0, 1),
        )
        db.execute(
            "INSERT INTO barbers (name, phone, is_active) VALUES (?, ?, ?)",
            ("Test Barber", "5555555555", 1),
        )
        db.commit()

    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def create_future_booking(app, hours_ahead=2):
    """Helper to create a booking in the future."""
    with app.app_context():
        now = datetime.now(SHOP_TIMEZONE)
        start = now + timedelta(hours=hours_ahead)
        end = start + timedelta(minutes=30)

        booking_id = execute_db(
            """
            INSERT INTO appointments 
            (customer_name, customer_phone, service_id, barber_id,
             start_time, end_time, status, booking_code, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Test Customer",
                "5141234567",
                1,
                1,
                start.isoformat(),
                end.isoformat(),
                "booked",
                "TESTCODE",
                now.isoformat(),
                now.isoformat(),
            ),
        )
    return booking_id


def test_successful_cancellation(client, app):
    """Test successful cancellation more than 30 minutes before start."""
    booking_id = create_future_booking(app, hours_ahead=2)

    csrf = _get_csrf(client)

    response = client.post(
        f"/api/booking/{booking_id}/cancel",
        json={"phone": "5141234567"},
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True

    # Verify booking is deleted
    with app.app_context():
        booking = query_db("SELECT * FROM appointments WHERE id = ?", (booking_id,), one=True)
        assert booking is None

        # Verify cancellation record exists
        cancellation = query_db(
            "SELECT * FROM cancellations WHERE booking_id = ?", (booking_id,), one=True
        )
        assert cancellation is not None
        assert cancellation["customer_name"] == "Test Customer"
        assert cancellation["customer_phone"] == "5141234567"
        assert cancellation["cancelled_by"] == "customer"


def test_cancellation_within_30_minutes(client, app):
    """Test cancellation rejected within 30 minutes of start."""
    booking_id = create_future_booking(app, hours_ahead=0.4)  # 24 minutes ahead

    csrf = _get_csrf(client)

    response = client.post(
        f"/api/booking/{booking_id}/cancel",
        json={"phone": "5141234567"},
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["ok"] is False
    assert "30 minutes" in data["error"]

    # Verify booking still exists
    with app.app_context():
        booking = query_db("SELECT * FROM appointments WHERE id = ?", (booking_id,), one=True)
        assert booking is not None

        # Verify no cancellation record
        cancellation = query_db(
            "SELECT * FROM cancellations WHERE booking_id = ?", (booking_id,), one=True
        )
        assert cancellation is None


def test_cancellation_past_booking(client, app):
    """Test cancellation rejected if booking is in the past."""
    with app.app_context():
        now = datetime.now(SHOP_TIMEZONE)
        past = now - timedelta(hours=1)
        past_end = past + timedelta(minutes=30)

        booking_id = execute_db(
            """
            INSERT INTO appointments 
            (customer_name, customer_phone, service_id, barber_id,
             start_time, end_time, status, booking_code, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Test Customer",
                "5141234567",
                1,
                1,
                past.isoformat(),
                past_end.isoformat(),
                "booked",
                "TESTCODE",
                now.isoformat(),
                now.isoformat(),
            ),
        )

    csrf = _get_csrf(client)

    response = client.post(
        f"/api/booking/{booking_id}/cancel",
        json={"phone": "5141234567"},
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["ok"] is False
    assert "past" in data["error"].lower()

    # Verify booking still exists
    with app.app_context():
        booking = query_db("SELECT * FROM appointments WHERE id = ?", (booking_id,), one=True)
        assert booking is not None


def test_cancellation_phone_mismatch(client, app):
    """Test cancellation rejected if phone doesn't match."""
    booking_id = create_future_booking(app, hours_ahead=2)

    csrf = _get_csrf(client)

    response = client.post(
        f"/api/booking/{booking_id}/cancel",
        json={"phone": "9999999999"},
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )

    assert response.status_code == 403
    data = response.get_json()
    assert data["ok"] is False
    assert "not match" in data["error"]

    # Verify booking still exists
    with app.app_context():
        booking = query_db("SELECT * FROM appointments WHERE id = ?", (booking_id,), one=True)
        assert booking is not None

        # Verify no cancellation record
        cancellation = query_db(
            "SELECT * FROM cancellations WHERE booking_id = ?", (booking_id,), one=True
        )
        assert cancellation is None
