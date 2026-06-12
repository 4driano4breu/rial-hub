from flask import Blueprint

usinagem_bp = Blueprint("usinagem", __name__, template_folder="../../../templates/usinagem")

from app.blueprints.usinagem import routes  # noqa: E402, F401
