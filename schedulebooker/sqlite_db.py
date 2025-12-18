# schedulebooker/sqlite_db.py

import os
import sqlite3
from flask import current_app, g

def init_app(app):
    """Run this from create_app() to set up the DB path + teardown."""

    # Ensure instance folder exists (same as your old code)
    os.makedirs(app.instance_path, exist_ok=True)

    # Build full DB path inside instance/
    db_path = os.path.join(
        app.instance_path,
        app.config.get("DATABASE", "appointments.db")
    )
    app.config["DATABASE_PATH"] = db_path

    @app.teardown_appcontext
    def close_db(e=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()


def get_db():
    """Use this in your routes instead of the old global get_db()."""

    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
    return g.db
def query_db(query, args=(), one=False):
    """Run a SELECT query and return rows (or one row)."""
    cur = get_db().execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows

def execute_db(query, args=()):
    """Run INSERT/UPDATE/DELETE and commit. Returns lastrowid."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id
