from __future__ import annotations

from flask import jsonify, request

from ...repositories import public_booking_repository as booking_repo
from ...services.booking_service import build_time_slots, parse_date_or_default
from . import api_v1_bp


@api_v1_bp.get("/health")
def health():
    return jsonify({"ok": True, "version": "v1"}), 200


@api_v1_bp.get("/services")
def services():
    return jsonify({"ok": True, "services": booking_repo.list_active_services()}), 200


@api_v1_bp.get("/barbers")
def barbers():
    return jsonify({"ok": True, "barbers": booking_repo.list_active_barbers()}), 200


@api_v1_bp.get("/availability")
def availability():
    service_id = request.args.get("service_id", type=int)
    selected_date_str = request.args.get("date")
    selected_barber_id = request.args.get("barber_id", type=int)

    if not service_id:
        return jsonify({"ok": False, "error": "service_id is required"}), 400

    service = booking_repo.get_active_service(service_id)
    if not service:
        return jsonify({"ok": False, "error": "Invalid service_id"}), 404

    selected_date_str, day = parse_date_or_default(selected_date_str)
    if not day:
        return jsonify({"ok": False, "error": "Invalid date format (expected YYYY-MM-DD)"}), 400

    barbers = booking_repo.list_active_barbers()
    duration_min = int(service.get("duration_min") or 30)
    time_slots = build_time_slots(day, duration_min, barbers, selected_barber_id)

    return (
        jsonify(
            {
                "ok": True,
                "service": service,
                "barbers": barbers,
                "selected_date": selected_date_str,
                "selected_barber_id": selected_barber_id,
                "time_slots": time_slots,
            }
        ),
        200,
    )
