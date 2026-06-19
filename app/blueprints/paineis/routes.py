import json
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required

from app.blueprints.paineis import paineis_bp
from app.extensions import db
from app.models import Painel

MODULOS_DISPONIVEIS = [
    ("insumos",      "Gestão de Insumos (Usinagem)"),
    ("faturamento",  "Gestão de Notas Fiscais"),
    ("producao",     "Registro de Produção"),
    ("formularios",  "Coleta de Campo"),
    ("equipamentos", "Gestão de Equipamentos"),
]


def _require_admin(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.has_role("ADMIN", "SUPERADMIN"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


@paineis_bp.route("/")
@login_required
def index():
    paineis = (Painel.query
        .filter_by(org_id=current_user.org_id, ativo=True)
        .order_by(Painel.criado_em.asc())
        .all())
    return render_template("paineis/index.html", paineis=paineis)


@paineis_bp.route("/novo", methods=["GET", "POST"])
@_require_admin
def novo():
    if request.method == "POST":
        nome   = request.form.get("nome", "").strip()
        slug   = request.form.get("slug", "").strip().lower().replace(" ", "-")
        modulo = request.form.get("modulo_fonte", "")
        desc   = request.form.get("descricao", "").strip()
        icone  = request.form.get("icone", "📊").strip() or "📊"
        cor    = request.form.get("cor", "#3b82f6").strip() or "#3b82f6"
        filtros_raw = request.form.get("filtros", "{}").strip()

        erros = []
        if not nome:
            erros.append("Nome obrigatório.")
        if not slug:
            erros.append("Slug obrigatório.")
        if modulo not in [m[0] for m in MODULOS_DISPONIVEIS]:
            erros.append("Módulo inválido.")
        if Painel.query.filter_by(org_id=current_user.org_id, slug=slug).first():
            erros.append(f"Já existe um painel com o slug '{slug}'.")

        try:
            filtros = json.loads(filtros_raw) if filtros_raw else {}
        except Exception:
            filtros = {}

        if erros:
            for e in erros:
                flash(e, "error")
            return render_template("paineis/form.html",
                                   titulo="Novo Painel",
                                   modulos=MODULOS_DISPONIVEIS,
                                   form=request.form)

        painel = Painel(
            org_id=current_user.org_id,
            slug=slug,
            nome=nome,
            descricao=desc,
            modulo_fonte=modulo,
            filtros=filtros,
            config_visual={"icone": icone, "cor": cor},
        )
        db.session.add(painel)
        db.session.commit()
        flash(f"Painel '{nome}' criado.", "ok")
        return redirect(url_for("paineis.index"))

    return render_template("paineis/form.html",
                           titulo="Novo Painel",
                           modulos=MODULOS_DISPONIVEIS,
                           form={})


@paineis_bp.route("/<slug>/configurar", methods=["GET", "POST"])
@_require_admin
def configurar(slug):
    painel = Painel.query.filter_by(org_id=current_user.org_id, slug=slug).first_or_404()

    if request.method == "POST":
        painel.nome      = request.form.get("nome", painel.nome).strip()
        painel.descricao = request.form.get("descricao", "").strip()
        icone = request.form.get("icone", "📊").strip() or "📊"
        cor   = request.form.get("cor", "#3b82f6").strip() or "#3b82f6"
        painel.config_visual = {"icone": icone, "cor": cor}
        filtros_raw = request.form.get("filtros", "{}").strip()
        try:
            painel.filtros = json.loads(filtros_raw) if filtros_raw else {}
        except Exception:
            pass
        db.session.commit()
        flash("Painel atualizado.", "ok")
        return redirect(url_for("paineis.index"))

    return render_template("paineis/form.html",
                           titulo="Configurar Painel",
                           painel=painel,
                           modulos=MODULOS_DISPONIVEIS,
                           form={
                               "nome": painel.nome,
                               "slug": painel.slug,
                               "descricao": painel.descricao or "",
                               "modulo_fonte": painel.modulo_fonte,
                               "icone": (painel.config_visual or {}).get("icone", "📊"),
                               "cor":   (painel.config_visual or {}).get("cor", "#3b82f6"),
                               "filtros": json.dumps(painel.filtros or {}, ensure_ascii=False),
                           })


@paineis_bp.route("/<slug>")
@login_required
def detalhe(slug):
    painel = Painel.query.filter_by(org_id=current_user.org_id, slug=slug).first_or_404()
    return render_template("paineis/detalhe.html", painel=painel)
