from flask import render_template
from app.blueprints.usinagem import usinagem_bp


@usinagem_bp.route("/")
def index():
    return render_template("usinagem/index.html")
