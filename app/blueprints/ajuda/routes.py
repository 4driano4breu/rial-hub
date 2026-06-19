from flask import render_template, abort

from app.blueprints.ajuda import ajuda_bp

_SECOES = {
    "primeiros-passos": "Primeiros Passos",
    "usinagem": "Usinagem CBUQ",
    "faturamento": "Faturamento NFS-e",
    "notas": "Notas de Medição",
    "equipamentos": "Gestão de Equipamentos",
    "coleta": "Coleta de Campo",
    "dados": "Gestão de Dados",
    "ferramentas": "Ferramentas",
    "admin": "Administração",
}


@ajuda_bp.route("/")
def index():
    return render_template("ajuda/index.html", secoes=_SECOES)


@ajuda_bp.route("/<secao>")
def secao(secao):
    if secao not in _SECOES:
        abort(404)
    return render_template(f"ajuda/{secao}.html", titulo=_SECOES[secao], secoes=_SECOES)
