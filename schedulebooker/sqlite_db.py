import os
import sqlite3

from flask import current_app, g


def init_app(app):
    app.config["DATABASE_PATH"] = os.path.join(
        app.instance_path,
        app.config.get("DATABASE", "appointments.db"),
    )
    os.makedirs(app.instance_path, exist_ok=True)
    app.teardown_appcontext(close_db)


def _table_exists(db: sqlite3.Connection, table_name: str) -> bool:
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_users_password_hash_column(db: sqlite3.Connection) -> None:
    # If schema isn't initialized yet, skip.
    if not _table_exists(db, "users"):
        return

    cols = {r["name"] for r in db.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        db.commit()


def _ensure_runtime_migrations(db: sqlite3.Connection) -> None:
    _ensure_users_password_hash_column(db)
    _ensure_barbers_phone_column(db)
    _ensure_admin_settings_columns(db)


def _ensure_admin_settings_columns(db: sqlite3.Connection) -> None:
    """Add email and phone columns to admin_users if missing."""
    if not _table_exists(db, "admin_users"):
        return

    cols = {r["name"] for r in db.execute("PRAGMA table_info(admin_users)").fetchall()}

    if "email" not in cols:
        db.execute("ALTER TABLE admin_users ADD COLUMN email TEXT")

    if "phone" not in cols:
        db.execute("ALTER TABLE admin_users ADD COLUMN phone TEXT")

    db.commit()


def get_db():
    if "db" not in g:
        # IMPORTANT: compute from *current* DATABASE (tests override DATABASE after create_app()).
        database = current_app.config.get("DATABASE", "appointments.db")
        db_path = (
            database
            if os.path.isabs(database)
            else os.path.join(current_app.instance_path, database)
        )

        # Keep DATABASE_PATH updated for debugging/visibility
        current_app.config["DATABASE_PATH"] = db_path

        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        _ensure_runtime_migrations(g.db)

    return g.db


def close_db(_e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid


def _ensure_barbers_phone_column(db: sqlite3.Connection) -> None:
    if not _table_exists(db, "barbers"):
        return

    cols = {r["name"] for r in db.execute("PRAGMA table_info(barbers)").fetchall()}
    if "phone" not in cols:
        db.execute("ALTER TABLE barbers ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        db.commit()
