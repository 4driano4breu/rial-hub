from flask import render_template, send_from_directory, current_app
from pathlib import Path
from app.blueprints.usinagem import usinagem_bp


def _dashboard(filename: str):
    folder = Path(current_app.static_folder) / "ferramentas" / "usinagem"
    return send_from_directory(folder, filename)


@usinagem_bp.route("/")
def index():
    return render_template("usinagem/index.html")


@usinagem_bp.route("/guariroba")
def guariroba():
    return _dashboard("dashboard_aguas_guariroba.html")


@usinagem_bp.route("/aegea")
def aegea():
    return _dashboard("Dashboard AEGEA.html")


@usinagem_bp.route("/geral")
def geral():
    return _dashboard("Dashboard Geral.html")
