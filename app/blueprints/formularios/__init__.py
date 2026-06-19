from flask import Blueprint

formularios_bp = Blueprint("formularios", __name__, url_prefix="/formularios")

from app.blueprints.formularios import routes  # noqa
