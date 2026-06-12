from flask import render_template
from app.blueprints.faturamento import faturamento_bp


@faturamento_bp.route("/")
def index():
    return render_template("faturamento/index.html")
