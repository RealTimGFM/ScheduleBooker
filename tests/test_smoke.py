import pytest
from flask import Flask

from schedulebooker import create_app
from schedulebooker.sqlite_db import get_db


@pytest.fixture()
def app(tmp_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "test.db"),  # isolated DB for tests
    )

    # Initialize schema + seed minimal data needed by /services
    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql") as f:
            db.executescript(f.read().decode("utf-8"))

        # Seed at least 1 active service so /services returns something
        db.execute(
            """
            INSERT OR IGNORE INTO services
              (name, category, duration_min, price, price_is_from, price_label, is_active, is_popular, sort_order)
            VALUES
              (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Test Service", "Homme", 30, 15.0, 0, None, 1, 1, 1),
        )
        db.commit()

    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_create_app_returns_flask_app():
    app = create_app()
    assert isinstance(app, Flask)


def test_blueprints_registered():
    app = create_app()
    assert "auth" in app.blueprints
    assert "appointments" in app.blueprints
    assert "public" in app.blueprints
    assert "admin" in app.blueprints


def test_public_services_route(client):
    r = client.get("/services")
    assert r.status_code == 200

    # If templates aren't present, your backend returns JSON fallback
    if r.is_json:
        data = r.get_json()
        assert data["template"] == "public/services.html"
        assert "most_popular_services" in data["context"]
        assert "other_services" in data["context"]
