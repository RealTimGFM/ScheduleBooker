from flask import Flask, redirect, url_for

from . import sqlite_db


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    from .extensions import csrf, limiter
    csrf.init_app(app)
    limiter.init_app(app)
    import os

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", os.urandom(24).hex()),
        DATABASE="appointments.db",
    )
    app.config.update(
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    app.config.from_pyfile("config.py", silent=True)
    sqlite_db.init_app(app)


    @app.after_request
    def add_security_headers(response):
        # Only add HSTS if HTTPS is enforced
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # CSP: Allow self + CDN for static assets
        csp = (
            "default-src 'self'; "
            "script-src 'self' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self';"
        )
        response.headers["Content-Security-Policy"] = csp
        
        return response

    from .admin import admin_bp
    from .appointments import appointments_bp
    from .auth import auth_bp
    from .public import public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(appointments_bp)

    # New
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return redirect(url_for("appointments.list_appointments"))

    return app
