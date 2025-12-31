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


def get_db():
    if "db" not in g:
        db_path = current_app.config["DATABASE_PATH"]
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
