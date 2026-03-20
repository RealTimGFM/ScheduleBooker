from __future__ import annotations

from ..sqlite_db import execute_db, query_db


def list_active_services() -> list[dict]:
    rows = query_db(
        "SELECT id, name, category, duration_min, price, price_is_from, price_label, is_popular "
        "FROM services WHERE is_active = 1 "
        "ORDER BY sort_order ASC, name ASC"
    )
    return [dict(r) for r in rows]


def list_active_barbers() -> list[dict]:
    rows = query_db("SELECT id, name, is_active FROM barbers WHERE is_active = 1 ORDER BY name ASC")
    return [dict(r) for r in rows]


def get_active_service(service_id: int) -> dict | None:
    row = query_db(
        "SELECT id, name, category, duration_min, price, price_is_from, price_label "
        "FROM services WHERE id = ? AND is_active = 1",
        (service_id,),
        one=True,
    )
    return dict(row) if row else None


def get_active_barber(barber_id: int) -> dict | None:
    row = query_db(
        "SELECT id, name, is_active FROM barbers WHERE id = ? AND is_active = 1",
        (barber_id,),
        one=True,
    )
    return dict(row) if row else None


def list_bookings_for_day(day_start_iso: str, day_end_iso: str) -> list[dict]:
    rows = query_db(
        """
        SELECT id, barber_id, service_id, start_time, end_time, status, customer_phone, customer_email, user_id
        FROM appointments
        WHERE status != 'cancelled' AND start_time >= ? AND start_time < ?
        """,
        (day_start_iso, day_end_iso),
    )
    return [dict(r) for r in rows]


def get_service_duration_lookup() -> dict[int, int]:
    rows = query_db("SELECT id, duration_min FROM services")
    return {int(r["id"]): int(r["duration_min"] or 30) for r in rows}


def count_bookings_for_contact_on_day(
    *,
    day_start_iso: str,
    day_end_iso: str,
    phone: str | None,
    email: str | None,
) -> int:
    clauses = []
    args: list[object] = [day_start_iso, day_end_iso]

    if phone:
        clauses.append("customer_phone = ?")
        args.append(phone)
    if email:
        clauses.append("customer_email = ?")
        args.append(email)

    if not clauses:
        return 0

    where_contact = " OR ".join(clauses)
    row = query_db(
        "SELECT COUNT(*) AS cnt FROM appointments "
        "WHERE status != 'cancelled' AND start_time >= ? AND start_time < ? "
        f"AND ({where_contact})",
        tuple(args),
        one=True,
    )
    return int(row["cnt"]) if row else 0


def get_booking_for_cancellation(booking_id: int, *, booked_only: bool = True):
    sql = """
        SELECT a.*, s.name AS service_name, b.name AS barber_name
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN barbers b ON a.barber_id = b.id
        WHERE a.id = ?
    """
    if booked_only:
        sql += " AND a.status = 'booked'"

    return query_db(sql, (booking_id,), one=True)


def is_booking_code_taken(code: str) -> bool:
    return bool(
        query_db(
            "SELECT 1 FROM appointments WHERE booking_code = ? LIMIT 1",
            (code,),
            one=True,
        )
    )


def create_appointment(
    *,
    user_id: int | None,
    barber_id: int | None,
    service_id: int,
    customer_name: str,
    customer_phone: str | None,
    customer_email: str | None,
    start_time_iso: str,
    end_time_iso: str,
    notes: str,
    status: str,
    booking_code: str,
    created_at_iso: str,
    updated_at_iso: str,
) -> int:
    return execute_db(
        "INSERT INTO appointments "
        "(user_id, barber_id, service_id, customer_name, customer_phone, customer_email, "
        " start_time, end_time, notes, status, booking_code, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            barber_id,
            service_id,
            customer_name,
            customer_phone,
            customer_email,
            start_time_iso,
            end_time_iso,
            notes,
            status,
            booking_code,
            created_at_iso,
            updated_at_iso,
        ),
    )


def get_booking_with_details(booking_id: int) -> dict | None:
    row = query_db(
        "SELECT a.*, s.name AS service_name, b.name AS barber_name "
        "FROM appointments a "
        "LEFT JOIN services s ON s.id = a.service_id "
        "LEFT JOIN barbers b ON b.id = a.barber_id "
        "WHERE a.id = ?",
        (booking_id,),
        one=True,
    )
    return dict(row) if row else None


def find_bookings_by_contact(phone: str | None, email: str | None) -> list[dict]:
    if not phone and not email:
        return []

    clauses = []
    args: list[object] = []

    if phone:
        clauses.append("customer_phone = ?")
        args.append(phone)
    if email:
        clauses.append("customer_email = ?")
        args.append(email)

    where_contact = " OR ".join(clauses)
    rows = query_db(
        "SELECT a.id, a.start_time, a.end_time, a.status, a.service_id, a.barber_id, "
        "       a.customer_name, a.customer_phone, a.customer_email, a.notes, "
        "       s.name AS service_name, b.name AS barber_name "
        "FROM appointments a "
        "LEFT JOIN services s ON s.id = a.service_id "
        "LEFT JOIN barbers b ON b.id = a.barber_id "
        f"WHERE ({where_contact}) "
        "ORDER BY a.start_time DESC",
        tuple(args),
    )
    return [dict(r) for r in rows]


def insert_cancellation(
    *,
    booking_id: int,
    customer_name: str,
    customer_phone: str | None,
    customer_email: str | None,
    barber_id: int | None,
    barber_name: str | None,
    service_id: int | None,
    service_name: str | None,
    start_datetime: str,
    end_datetime: str | None,
    cancelled_at: str,
    cancelled_by: str,
) -> int:
    return execute_db(
        """
        INSERT INTO cancellations
        (booking_id, customer_name, customer_phone, customer_email,
         barber_id, barber_name, service_id, service_name,
         start_datetime, end_datetime, cancelled_at, cancelled_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
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
            cancelled_by,
        ),
    )


def mark_appointment_cancelled(booking_id: int, *, updated_at: str) -> int:
    return execute_db(
        "UPDATE appointments SET status = 'cancelled', updated_at = ? WHERE id = ?",
        (updated_at, booking_id),
    )
