from flask import Blueprint

dados_bp = Blueprint(
    "dados", __name__,
    url_prefix="/admin/dados",
)

from app.blueprints.dados import routes  # noqa: E402, F401
