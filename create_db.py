# create_db.py
from datetime import datetime
from schedulebooker import create_app
from schedulebooker.sqlite_db import get_db, execute_db

app = create_app()

with app.app_context():
    db = get_db()
    # Run schema
    with app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))
    db.commit()

    # Insert default services if table empty
    rows = db.execute("SELECT COUNT(*) AS c FROM services").fetchone()
    if rows["c"] == 0:
        execute_db("INSERT INTO services (name) VALUES (?)", ("Haircut",))
        execute_db("INSERT INTO services (name) VALUES (?)", ("Shampooing",))
        execute_db("INSERT INTO services (name) VALUES (?)", ("Shaving",))

    print("Database initialized and default services added.")
