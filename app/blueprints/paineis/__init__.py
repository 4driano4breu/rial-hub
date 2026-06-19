from flask import Blueprint
paineis_bp = Blueprint("paineis", __name__, url_prefix="/paineis")
from app.blueprints.paineis import routes  # noqa
