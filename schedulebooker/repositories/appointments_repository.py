from __future__ import annotations

from ..sqlite_db import execute_db, query_db


def get_user_phone(user_id: int):
    return query_db("SELECT phone_number FROM users WHERE id = ?", (user_id,), one=True)


def claim_guest_bookings_for_phone(user_id: int, phone: str) -> int:
    return execute_db(
        """
        UPDATE appointments
        SET user_id = ?
        WHERE user_id IS NULL AND customer_phone = ?
        """,
        (user_id, phone),
    )


def list_user_appointments(user_id: int):
    return query_db(
        """
        SELECT a.*, s.name AS service_name
        FROM appointments a
        LEFT JOIN services s ON s.id = a.service_id
        WHERE a.user_id = ?
        ORDER BY a.start_time ASC
        """,
        (user_id,),
    )


def list_service_choices():
    return query_db("SELECT id, name FROM services ORDER BY name")


def get_user_appointment(appt_id: int, user_id: int):
    return query_db(
        "SELECT * FROM appointments WHERE id = ? AND user_id = ?",
        (appt_id, user_id),
        one=True,
    )


def create_user_appointment(
    *,
    user_id: int,
    customer_name: str,
    service_id: int,
    start_time: str,
    end_time: str,
    notes: str,
    created_at: str,
    updated_at: str,
) -> int:
    return execute_db(
        """
        INSERT INTO appointments
            (user_id, customer_name, service_id, start_time, end_time, notes, status, created_at, updated_at)
        VALUES
            (?, ?, ?, ?, ?, ?, 'booked', ?, ?)
        """,
        (
            user_id,
            customer_name,
            service_id,
            start_time,
            end_time,
            notes,
            created_at,
            updated_at,
        ),
    )


def update_user_appointment(
    *,
    appt_id: int,
    user_id: int,
    customer_name: str,
    service_id: int,
    start_time: str,
    end_time: str,
    notes: str,
    updated_at: str,
) -> int:
    return execute_db(
        """
        UPDATE appointments
        SET customer_name = ?, service_id = ?, start_time = ?, end_time = ?, notes = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            customer_name,
            service_id,
            start_time,
            end_time,
            notes,
            updated_at,
            appt_id,
            user_id,
        ),
    )


def delete_user_appointment(appt_id: int, user_id: int) -> int:
    return execute_db("DELETE FROM appointments WHERE id = ? AND user_id = ?", (appt_id, user_id))
