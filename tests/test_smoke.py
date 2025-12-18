from flask import Flask

from schedulebooker import create_app


def test_create_app_returns_flask_app():
    app = create_app()
    assert isinstance(app, Flask)


def test_blueprints_registered():
    app = create_app()
    # Based on your package structure, these are the likely blueprint names
    assert "auth" in app.blueprints
    assert "appointments" in app.blueprints
