from flask import Blueprint

viario_bp = Blueprint("viario", __name__)

from app.blueprints.viario import routes  # noqa: E402,F401
