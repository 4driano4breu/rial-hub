import json
from datetime import date, timedelta
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from sqlalchemy import func

from app.blueprints.paineis import paineis_bp
from app.extensions import db
from app.models import (Painel, UsinagemRegistro, FaturamentoNota,
                        OperacaoProducao, FormularioTemplate, FormularioResposta,
                        Equipamento, ChecklistExecucao)

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
    org_id = current_user.org_id
    filtros = painel.filtros or {}
    stats = {}
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    if painel.modulo_fonte == "insumos":
        q = UsinagemRegistro.query.filter_by(org_id=org_id, excluido=False)
        if filtros.get("regiao"):
            q = q.filter(UsinagemRegistro.regiao == filtros["regiao"])
        if filtros.get("contrato"):
            q = q.filter(UsinagemRegistro.contrato == filtros["contrato"])
        total = q.count()
        peso_total = q.with_entities(func.sum(UsinagemRegistro.peso_liquido)).scalar() or 0
        peso_mes = q.filter(UsinagemRegistro.data_operacao >= inicio_mes)\
                    .with_entities(func.sum(UsinagemRegistro.peso_liquido)).scalar() or 0
        regioes = [r[0] for r in q.with_entities(UsinagemRegistro.regiao).distinct().all() if r[0]]
        stats = {"total": total, "peso_total": float(peso_total),
                 "peso_mes": float(peso_mes), "regioes": regioes,
                 "label_total": "Registros", "label_peso": "Toneladas (total)",
                 "label_mes": f"Toneladas ({inicio_mes.strftime('%b/%Y')})"}

    elif painel.modulo_fonte == "faturamento":
        q = FaturamentoNota.query.filter_by(org_id=org_id, excluido=False)
        if filtros.get("contrato"):
            q = q.filter(FaturamentoNota.contrato == filtros["contrato"])
        if filtros.get("orgao"):
            q = q.filter(FaturamentoNota.orgao == filtros["orgao"])
        total = q.count()
        recebido = q.filter_by(recebido=True).count()
        pendente = total - recebido
        bruto_total = q.with_entities(func.sum(FaturamentoNota.bruto)).scalar() or 0
        liquido_total = q.with_entities(func.sum(FaturamentoNota.liquido)).scalar() or 0
        stats = {"total": total, "recebido": recebido, "pendente": pendente,
                 "bruto_total": float(bruto_total), "liquido_total": float(liquido_total),
                 "label_total": "Notas Fiscais", "label_recebido": "Recebidas",
                 "label_pendente": "Pendentes"}

    elif painel.modulo_fonte == "producao":
        q = OperacaoProducao.query.filter_by(org_id=org_id)
        if filtros.get("modo"):
            q = q.filter(OperacaoProducao.modo == filtros["modo"])
        total = q.count()
        mes = q.filter(OperacaoProducao.data_operacao >= inicio_mes).count()
        caminhoes_total = q.with_entities(func.sum(OperacaoProducao.total_caminhoes)).scalar() or 0
        stats = {"total": total, "mes": mes,
                 "caminhoes_total": int(caminhoes_total),
                 "label_total": "Operações", "label_mes": f"Operações ({inicio_mes.strftime('%b/%Y')})"}

    elif painel.modulo_fonte == "formularios":
        tpl_q = FormularioTemplate.query.filter_by(org_id=org_id, ativo=True)
        if filtros.get("template_slug"):
            tpl_q = tpl_q.filter(FormularioTemplate.slug == filtros["template_slug"])
        templates = tpl_q.all()
        tpl_ids = [t.id for t in templates]
        resp_q = FormularioResposta.query.filter(
            FormularioResposta.org_id == org_id,
            FormularioResposta.template_id.in_(tpl_ids) if tpl_ids else db.false()
        )
        total = resp_q.count()
        mes = resp_q.filter(FormularioResposta.criado_em >= inicio_mes).count()
        stats = {"total": total, "mes": mes, "templates": len(templates),
                 "label_total": "Respostas", "label_mes": f"Respostas ({inicio_mes.strftime('%b/%Y')})"}

    elif painel.modulo_fonte == "equipamentos":
        eq_q = Equipamento.query.filter_by(org_id=org_id, ativo=True)
        if filtros.get("tipo"):
            eq_q = eq_q.filter(Equipamento.tipo == filtros["tipo"])
        equipamentos_count = eq_q.count()
        eq_ids = [e.id for e in eq_q.all()]
        chk_q = ChecklistExecucao.query.filter(
            ChecklistExecucao.org_id == org_id,
            ChecklistExecucao.equipamento_id.in_(eq_ids) if eq_ids else db.false()
        )
        total = chk_q.count()
        mes = chk_q.filter(ChecklistExecucao.data_execucao >= inicio_mes).count()
        completo = chk_q.filter_by(status="COMPLETO").count()
        stats = {"total": total, "mes": mes, "equipamentos": equipamentos_count,
                 "completo": completo,
                 "label_total": "Checklists", "label_mes": f"Checklists ({inicio_mes.strftime('%b/%Y')})"}

    return render_template("paineis/detalhe.html", painel=painel, stats=stats)
