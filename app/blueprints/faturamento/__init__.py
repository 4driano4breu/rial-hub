from flask import Blueprint

faturamento_bp = Blueprint("faturamento", __name__, template_folder="../../../templates/faturamento")

from app.blueprints.faturamento import routes  # noqa: E402, F401
