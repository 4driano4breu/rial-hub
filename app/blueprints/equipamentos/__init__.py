from flask import Blueprint

equipamentos_bp = Blueprint("equipamentos", __name__, template_folder="../../../templates/equipamentos")

from app.blueprints.equipamentos import routes  # noqa: E402, F401
