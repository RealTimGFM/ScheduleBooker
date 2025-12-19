# create_db.py
from werkzeug.security import generate_password_hash

from schedulebooker import create_app
from schedulebooker.sqlite_db import execute_db, get_db

app = create_app()

with app.app_context():
    db = get_db()

    # Run schema
    with app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))
    db.commit()

    # Seed services
    rows = db.execute("SELECT COUNT(*) AS c FROM services").fetchone()
    if rows["c"] == 0:
        # in create_db.py seed section
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
    rows = db.execute("SELECT COUNT(*) AS c FROM barbers").fetchone()
    if rows["c"] == 0:
        for name in ["Barber A", "Barber B", "Barber C"]:
            execute_db("INSERT INTO barbers (name, is_active) VALUES (?, 1)", (name,))

    # Seed default admin account (hashed password)
    rows = db.execute("SELECT COUNT(*) AS c FROM admin_users").fetchone()
    if rows["c"] == 0:
        execute_db(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            ("T", generate_password_hash("1")),
        )

    print("Database initialized and seeds added (services, barbers, admin).")
