from flask import Flask, redirect, url_for
from . import sqlite_db

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY="dev",            # required for session login
        DATABASE="appointments.db",
    )
    app.config.from_pyfile("config.py", silent=True)

    sqlite_db.init_app(app)

    from .auth import auth_bp
    from .appointments import appointments_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(appointments_bp)

    @app.route("/")
    def index():
        return redirect(url_for("appointments.list_appointments"))

    return app
