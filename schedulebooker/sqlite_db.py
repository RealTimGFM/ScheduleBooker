import os
import sqlite3

from flask import current_app, g

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:
    psycopg2 = None
    RealDictCursor = None


def init_app(app):
    app.config["DATABASE_PATH"] = os.path.join(
        app.instance_path,
        app.config.get("DATABASE", "appointments.db"),
    )
    os.makedirs(app.instance_path, exist_ok=True)
    app.teardown_appcontext(close_db)


def _get_database_url() -> str | None:
    # Prefer environment for production (Render/Neon), but allow config override in tests if needed
    return os.environ.get("DATABASE_URL") or current_app.config.get("DATABASE_URL")


def _is_postgres_url(url: str | None) -> bool:
    if not url:
        return False
    return url.startswith("postgres://") or url.startswith("postgresql://")


def _pg_sql(sql: str) -> str:
    # App uses SQLite-style placeholders ("?"). psycopg2 uses "%s".
    # This simple replacement matches your current query style throughout the codebase.
    return sql.replace("?", "%s")


def _table_exists_sqlite(db: sqlite3.Connection, table_name: str) -> bool:
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_users_password_hash_column(db: sqlite3.Connection) -> None:
    # If schema isn't initialized yet, skip.
    if not _table_exists_sqlite(db, "users"):
        return

    cols = {r["name"] for r in db.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        db.commit()


def _ensure_barbers_phone_column(db: sqlite3.Connection) -> None:
    if not _table_exists_sqlite(db, "barbers"):
        return

    cols = {r["name"] for r in db.execute("PRAGMA table_info(barbers)").fetchall()}
    if "phone" not in cols:
        db.execute("ALTER TABLE barbers ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        db.commit()


def _ensure_admin_settings_columns(db: sqlite3.Connection) -> None:
    """Add email and phone columns to admin_users if missing."""
    if not _table_exists_sqlite(db, "admin_users"):
        return

    cols = {r["name"] for r in db.execute("PRAGMA table_info(admin_users)").fetchall()}

    if "email" not in cols:
        db.execute("ALTER TABLE admin_users ADD COLUMN email TEXT")

    if "phone" not in cols:
        db.execute("ALTER TABLE admin_users ADD COLUMN phone TEXT")

    db.commit()


def _ensure_runtime_migrations_sqlite(db: sqlite3.Connection) -> None:
    _ensure_users_password_hash_column(db)
    _ensure_barbers_phone_column(db)
    _ensure_admin_settings_columns(db)


def get_db():
    if "db" in g:
        return g.db

    db_url = _get_database_url()

    # ----------------------------
    # Postgres (Render/Neon)
    # ----------------------------
    if _is_postgres_url(db_url):
        if psycopg2 is None:
            raise RuntimeError(
                "psycopg2 is required for Postgres DATABASE_URL but is not installed."
            )

        conn = psycopg2.connect(db_url)
        g.db = conn
        g.db_backend = "postgres"
        return g.db

    # ----------------------------
    # SQLite (local dev / tests)
    # ----------------------------
    database = current_app.config.get("DATABASE", "appointments.db")
    db_path = (
        database
        if os.path.isabs(database)
        else os.path.join(current_app.instance_path, database)
    )

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    _ensure_runtime_migrations_sqlite(db)

    g.db = db
    g.db_backend = "sqlite"
    return g.db


def close_db(_e=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass


def query_db(query, args=(), one=False):
    db = get_db()
    backend = getattr(g, "db_backend", "sqlite")

    if backend == "postgres":
        q = _pg_sql(query)
        with db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, args)
            rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows

    cur = db.execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute_db(query, args=()):
    db = get_db()
    backend = getattr(g, "db_backend", "sqlite")

    if backend == "postgres":
        q = _pg_sql(query)
        last_id = None
        with db.cursor() as cur:
            cur.execute(q, args)
            # If caller used RETURNING, fetch it.
            if "RETURNING" in q.upper():
                try:
                    row = cur.fetchone()
                    if row:
                        last_id = row[0]
                except Exception:
                    last_id = None
        db.commit()
        return last_id

    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid
