# create_db.py
from __future__ import annotations

from werkzeug.security import generate_password_hash

from schedulebooker import create_app
from schedulebooker.sqlite_db import execute_db, get_db, query_db

app = create_app()


def _is_postgres() -> bool:
    import os
    from flask import current_app

    url = os.environ.get("DATABASE_URL") or current_app.config.get("DATABASE_URL")
    return bool(url) and (url.startswith("postgres://") or url.startswith("postgresql://"))


def _run_schema() -> None:
    db = get_db()

    if _is_postgres():
        # Postgres schema
        with app.open_resource("schema_postgres.sql") as f:
            sql = f.read().decode("utf-8")

        # Execute statements one-by-one
        for stmt in sql.split(";"):
            s = stmt.strip()
            if not s:
                continue
            execute_db(s)
        return

    # SQLite schema
    with app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))
    db.commit()


with app.app_context():
    _run_schema()

    # Seed services
    row = query_db("SELECT COUNT(*) AS c FROM services", one=True)
    if row and row["c"] == 0:
        services = [
            # name, category, duration_min, price, price_is_from, price_label, is_popular, sort_order
            ("Coupe (Homme)", "Homme", 30, 15.0, 0, None, 1, 1),
            ("Teinture (Homme)", "Homme", 60, 35.0, 1, None, 0, 2),
            ("Coupe (Femme)", "Femme", 60, 18.0, 1, None, 1, 10),
            ("Coupe + Placer (Femme)", "Femme", 60, 25.0, 1, None, 0, 11),
            ("Laver + Placer (Femme)", "Femme", 60, 20.0, 0, None, 0, 12),
            ("Teinture (Femme)", "Femme", 120, 70.0, 0, None, 0, 13),
            ("Permanent", "Femme", 120, 60.0, 0, None, 0, 14),
            ("Highlight", "Femme", 150, 120.0, 1, None, 0, 15),
            ("Lissage", "Femme", 180, 150.0, 1, None, 0, 16),
        ]

        for name, category, dur, price, price_is_from, price_label, popular, order in services:
            execute_db(
                """
                INSERT INTO services
                (name, category, duration_min, price, price_is_from, price_label, is_popular, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, category, dur, price, price_is_from, price_label, popular, order),
            )

    # Seed barbers
    row = query_db("SELECT COUNT(*) AS c FROM barbers", one=True)
    if row and row["c"] == 0:
        barbers = [
            ("Mr Thien", "(514) 277-3585"),
            ("Barber B", "5142222222"),
            ("Barber C", "5143333333"),
        ]
        for name, phone in barbers:
            execute_db(
                "INSERT INTO barbers (name, phone, is_active) VALUES (?, ?, 1)",
                (name, phone),
            )

    # Seed default admin account (hashed password)
    row = query_db("SELECT COUNT(*) AS c FROM admin_users", one=True)
    if row and row["c"] == 0:
        execute_db(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            ("T", generate_password_hash("1")),
        )

    print("Database initialized and seeds added.")
