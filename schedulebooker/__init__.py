import os

from flask import Flask, redirect, url_for

from . import sqlite_db


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        DATABASE="appointments.db",
    )
    app.config.from_pyfile("config.py", silent=True)

    # Environment should win in production. Fallback to config.py, then "dev".
    app.config["SECRET_KEY"] = (
        os.environ.get("SECRET_KEY")
        or app.config.get("SECRET_KEY")
        or "dev"
    )

    sqlite_db.init_app(app)

    from .admin import admin_bp
    from .appointments import appointments_bp
    from .auth import auth_bp
    from .public import public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(appointments_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return redirect(url_for("appointments.list_appointments"))

    return app