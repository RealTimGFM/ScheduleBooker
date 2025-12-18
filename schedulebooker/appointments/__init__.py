from flask import Blueprint

appointments_bp = Blueprint("appointments", __name__, url_prefix="/appointments")

from . import routes  # noqa
