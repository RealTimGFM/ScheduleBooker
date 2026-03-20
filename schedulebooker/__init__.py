import os

from dotenv import load_dotenv
from flask import Flask, redirect, url_for

from . import sqlite_db

load_dotenv()


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        DATABASE="appointments.db",
    )
    app.config.from_pyfile("config.py", silent=True)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or app.config.get("SECRET_KEY") or "dev"

    # EmailJS config
    app.config["EMAILJS_PUBLIC_KEY"] = os.environ.get("EMAILJS_PUBLIC_KEY", "").strip()
    app.config["EMAILJS_SERVICE_ID"] = os.environ.get("EMAILJS_SERVICE_ID", "").strip()
    app.config["EMAILJS_TEMPLATE_ID"] = os.environ.get("EMAILJS_TEMPLATE_ID", "").strip()
    app.config["APP_BASE_URL"] = os.environ.get("APP_BASE_URL", "").strip()

    sqlite_db.init_app(app)

    from .api.v1 import api_v1_bp
    from .admin import admin_bp
    from .appointments import appointments_bp
    from .auth import auth_bp
    from .public import public_bp

    app.register_blueprint(api_v1_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(appointments_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return redirect(url_for("appointments.list_appointments"))

    return app
