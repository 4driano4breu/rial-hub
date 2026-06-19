from flask import Blueprint

ajuda_bp = Blueprint("ajuda", __name__, url_prefix="/ajuda")

from app.blueprints.ajuda import routes  # noqa
