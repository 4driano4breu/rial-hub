from flask import send_from_directory, current_app, render_template
from pathlib import Path
from app.blueprints.ferramentas import ferramentas_bp


@ferramentas_bp.route("/")
def index():
    return render_template("ferramentas/index.html")


def _ferramenta(subdir: str, filename: str):
    folder = Path(current_app.static_folder) / "ferramentas" / subdir
    return send_from_directory(folder, filename)


@ferramentas_bp.route("/medicao")
def medicao():
    return _ferramenta("faz_tudo", "medicao_pavimentacao_v6.0.html")


@ferramentas_bp.route("/le-doc")
def le_doc():
    return _ferramenta("le_doc", "preenchimento.html")


@ferramentas_bp.route("/abastecimento")
def abastecimento():
    return _ferramenta("abastecimento", "Dashboard_Abastecimento.html")


@ferramentas_bp.route("/notas-html")
def notas_html():
    return _ferramenta("notas", "notas_037.html")
