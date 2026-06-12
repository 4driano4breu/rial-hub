from flask import Blueprint

ferramentas_bp = Blueprint("ferramentas", __name__, template_folder="../../../templates")

from app.blueprints.ferramentas import routes  # noqa: E402, F401
