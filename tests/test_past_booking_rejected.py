import pytest
from datetime import datetime, timedelta

from schedulebooker import create_app
from schedulebooker.public.routes import SHOP_TIMEZONE
from schedulebooker.sqlite_db import get_db


def _pick_past_non_monday(today):
    # Public flow blocks Monday before it blocks "past"; pick a past day that isn't Monday.
    for i in range(1, 15):
        d = today - timedelta(days=i)
        if d.weekday() != 0:
            return d
    return today - timedelta(days=1)


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

        # Seed service + barber for public booking flow
        db.execute(
            """
            INSERT OR IGNORE INTO services
              (name, category, duration_min, price, price_is_from, price_label, is_active, is_popular, sort_order)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Test Service", "Homme", 30, 15.0, 0, None, 1, 1, 1),
        )
        db.execute(
            "INSERT OR IGNORE INTO barbers (name, phone, is_active) VALUES (?, ?, ?)",
            ("Test Barber", "5555555555", 1),
        )

        # Seed a user for /appointments/new
        db.execute(
            "INSERT OR IGNORE INTO users (phone_number, name, password_hash) VALUES (?, ?, ?)",
            ("+10000000000", "Test User", "x"),
        )

        db.commit()

    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def _get_ids(app):
    with app.app_context():
        db = get_db()
        service_id = db.execute(
            "SELECT id FROM services WHERE name = ?",
            ("Test Service",),
        ).fetchone()[0]
        barber_id = db.execute(
            "SELECT id FROM barbers WHERE name = ?",
            ("Test Barber",),
        ).fetchone()[0]
        user_id = db.execute(
            "SELECT id FROM users WHERE phone_number = ?",
            ("+10000000000",),
        ).fetchone()[0]
    return service_id, barber_id, user_id


def test_public_book_finish_rejects_past_booking(client, app):
    service_id, barber_id, _ = _get_ids(app)

    today = datetime.now(SHOP_TIMEZONE).date()
    past_day = _pick_past_non_monday(today)

    r = client.post(
        "/book/finish",
        data={
            "service_id": service_id,
            "barber_id": barber_id,
            "date": past_day.isoformat(),
            "time": "11:00",
            "customer_name": "Test Customer",
            "customer_phone": "1234567890",
        },
    )

    assert r.status_code == 200
    assert b"Cannot book in the past" in r.data


def test_appointments_new_rejects_past_booking(client, app):
    service_id, _, user_id = _get_ids(app)

    today = datetime.now(SHOP_TIMEZONE).date()
    past_day = today - timedelta(days=1)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post(
        "/appointments/new",
        data={
            "customer_name": "Test Customer",
            "service_id": service_id,
            "date": past_day.isoformat(),
            "time": "12:00",
            "notes": "",
        },
    )

    assert r.status_code == 200
    assert b"Cannot book in the past" in r.data
