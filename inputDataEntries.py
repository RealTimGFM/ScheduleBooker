from __future__ import annotations

import argparse
import random
import secrets
from datetime import datetime, timedelta

from schedulebooker import create_app
from schedulebooker.sqlite_db import execute_db, query_db

app = create_app()

MARKER = "[income-demo-seed]"
NAME_PREFIX = "Income Demo"
PHONE_PREFIX = "514555"
EMAIL_DOMAIN = "demo.local"


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(timespec="seconds")


def make_code() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")


def clear_old_demo_rows() -> None:
    demo_appts = query_db(
        "SELECT id FROM appointments WHERE notes = ? OR customer_name LIKE ?",
        (MARKER, f"{NAME_PREFIX}%"),
    )
    ids = [int(row["id"]) for row in demo_appts]

    if ids:
        placeholders = ",".join(["?"] * len(ids))
        execute_db(
            f"DELETE FROM cancellations WHERE booking_id IN ({placeholders})",
            tuple(ids),
        )
        execute_db(
            f"DELETE FROM appointments WHERE id IN ({placeholders})",
            tuple(ids),
        )

    # Extra cleanup in case old demo cancellations exist without matching appointment ids.
    execute_db(
        "DELETE FROM cancellations WHERE customer_name LIKE ?",
        (f"{NAME_PREFIX}%",),
    )


def load_seed_dependencies() -> tuple[list[dict], list[dict]]:
    services = [
        dict(row)
        for row in query_db(
            "SELECT id, name, duration_min, price FROM services WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
        )
    ]
    barbers = [
        dict(row)
        for row in query_db(
            "SELECT id, name FROM barbers WHERE is_active = 1 ORDER BY id ASC"
        )
    ]

    if not services or not barbers:
        raise RuntimeError(
            "Missing services or barbers. Run 'python create_db.py' first so the base seed exists."
        )

    return services, barbers


def build_demo_datetimes(index: int, rng: random.Random, now: datetime) -> tuple[datetime, datetime | None, datetime]:
    # Spread rows across roughly the last 120 days so day/month/year views all have data.
    day_offset = rng.randint(0, 119)
    base_day = (now - timedelta(days=day_offset)).date()

    # Keep the times within shop hours and far enough in the past to count as completed today too.
    possible_starts = [11, 12, 13, 14, 15, 16, 17]
    start_hour = rng.choice(possible_starts)
    start_minute = rng.choice([0, 30])
    start_dt = datetime.combine(base_day, datetime.min.time()).replace(
        hour=start_hour,
        minute=start_minute,
    )

    # created_at is before the appointment start.
    created_at = start_dt - timedelta(days=rng.randint(1, 12), hours=rng.randint(1, 8))

    return start_dt, None, created_at


def seed_demo_rows(count: int) -> None:
    rng = random.Random(42)
    now = datetime.now()

    services, barbers = load_seed_dependencies()
    clear_old_demo_rows()

    booked_target = int(count * 0.8)
    cancelled_target = count - booked_target

    inserted_booked = 0
    inserted_cancelled = 0

    for i in range(count):
        service = rng.choice(services)
        barber = rng.choice(barbers)

        start_dt, _, created_at = build_demo_datetimes(i, rng, now)
        duration = int(service.get("duration_min") or 30)

        # Keep a few completed bookings with null end_time so the fallback logic is tested too.
        use_null_end = i % 11 == 0
        end_dt = None if use_null_end else start_dt + timedelta(minutes=duration)

        customer_num = i + 1
        customer_name = f"{NAME_PREFIX} {customer_num:03d}"
        customer_phone = f"{PHONE_PREFIX}{customer_num:04d}"[-10:]
        customer_email = f"income-demo-{customer_num:03d}@{EMAIL_DOMAIN}"
        booking_code = make_code()

        is_cancelled = i >= booked_target
        status = "cancelled" if is_cancelled else "booked"
        updated_at = (
            start_dt + timedelta(hours=1)
            if not is_cancelled
            else start_dt - timedelta(hours=rng.randint(2, 48))
        )

        appt_id = execute_db(
            """
            INSERT INTO appointments
            (
                user_id,
                barber_id,
                service_id,
                customer_name,
                customer_phone,
                customer_email,
                start_time,
                end_time,
                notes,
                status,
                booking_code,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                barber["id"],
                service["id"],
                customer_name,
                customer_phone,
                customer_email,
                iso(start_dt),
                iso(end_dt) if end_dt else None,
                MARKER,
                status,
                booking_code,
                iso(created_at),
                iso(updated_at),
            ),
        )

        if is_cancelled:
            cancelled_at = start_dt - timedelta(hours=rng.randint(2, 72))
            if cancelled_at < created_at:
                cancelled_at = created_at + timedelta(hours=1)
            if cancelled_at > now:
                cancelled_at = now - timedelta(hours=1)

            execute_db(
                """
                INSERT INTO cancellations
                (
                    booking_id,
                    customer_name,
                    customer_phone,
                    customer_email,
                    barber_id,
                    barber_name,
                    service_id,
                    service_name,
                    start_datetime,
                    end_datetime,
                    cancelled_at,
                    cancelled_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    appt_id,
                    customer_name,
                    customer_phone,
                    customer_email,
                    barber["id"],
                    barber["name"],
                    service["id"],
                    service["name"],
                    iso(start_dt),
                    iso(end_dt) if end_dt else None,
                    iso(cancelled_at),
                    "admin",
                ),
            )
            inserted_cancelled += 1
        else:
            inserted_booked += 1

    print("Demo income data inserted successfully.")
    print(f"Booked/completed rows: {inserted_booked}")
    print(f"Cancelled rows:        {inserted_cancelled}")
    print(f"Total rows inserted:   {count}")
    print("Use the Admin > Income page and switch between Day / Month / Year to see the seeded data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo appointment rows for the income tab.")
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="How many demo appointments to insert. Default: 100",
    )
    args = parser.parse_args()

    with app.app_context():
        seed_demo_rows(args.count)
