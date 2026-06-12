from flask import send_from_directory, current_app
from pathlib import Path
from app.blueprints.ferramentas import ferramentas_bp


def _static_ferramentas():
    return Path(current_app.static_folder) / "ferramentas"


@ferramentas_bp.route("/medicao")
def medicao():
    return send_from_directory(_static_ferramentas(), "medicao.html")


@ferramentas_bp.route("/le-doc")
def le_doc():
    return send_from_directory(_static_ferramentas(), "le-doc.html")


@ferramentas_bp.route("/abastecimento")
def abastecimento():
    return send_from_directory(_static_ferramentas(), "abastecimento.html")
