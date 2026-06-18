import json
from datetime import date, timedelta

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app.blueprints.equipamentos import equipamentos_bp
from app.extensions import db
from app.models import Equipamento, ChecklistTemplate, ChecklistExecucao


def _calcular_status(equip_id, org_id):
    ultima = ChecklistExecucao.query.filter_by(
        equipamento_id=equip_id, org_id=org_id
    ).order_by(ChecklistExecucao.data_execucao.desc()).first()

    if not ultima:
        return {"status": "CRITICO", "streak": 0, "ultima": None, "dias_atraso": None}

    dias_atraso = (date.today() - ultima.data_execucao).days

    # Calcular streak: dias consecutivos retroativos
    streak = 0
    d = date.today()
    while True:
        ex = ChecklistExecucao.query.filter_by(
            equipamento_id=equip_id, org_id=org_id, data_execucao=d
        ).first()
        if ex:
            streak += 1
            d -= timedelta(days=1)
        else:
            break

    if dias_atraso == 0:
        status = "EM_DIA"
    elif dias_atraso <= 2:
        status = "ATENCAO"
    else:
        status = "CRITICO"

    return {"status": status, "streak": streak, "ultima": ultima.data_execucao, "dias_atraso": dias_atraso}


@equipamentos_bp.route("/")
@login_required
def index():
    equips = Equipamento.query.filter_by(org_id=current_user.org_id, ativo=True).all()
    cards = []
    for e in equips:
        s = _calcular_status(e.id, current_user.org_id)
        cards.append({"equip": e, **s})
    return render_template("equipamentos/index.html", cards=cards)


@equipamentos_bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    templates = ChecklistTemplate.query.filter_by(org_id=current_user.org_id).all()
    if request.method == "POST":
        e = Equipamento(
            org_id=current_user.org_id,
            nome=request.form["nome"],
            tipo=request.form.get("tipo", ""),
            modelo=request.form.get("modelo", ""),
            ano=request.form.get("ano") or None,
            numero_serie=request.form.get("numero_serie", ""),
            placa=request.form.get("placa", ""),
            template_id=request.form.get("template_id") or None,
        )
        db.session.add(e)
        db.session.commit()
        flash(f"Equipamento '{e.nome}' cadastrado.", "ok")
        return redirect(url_for("equipamentos.index"))
    return render_template("equipamentos/novo.html", templates=templates)


@equipamentos_bp.route("/<int:equip_id>")
@login_required
def detalhe(equip_id):
    e = Equipamento.query.filter_by(id=equip_id, org_id=current_user.org_id).first_or_404()
    s = _calcular_status(e.id, current_user.org_id)

    # Histórico dos últimos 90 dias para o heatmap
    hoje = date.today()
    inicio = hoje - timedelta(days=89)
    execucoes = ChecklistExecucao.query.filter(
        ChecklistExecucao.equipamento_id == equip_id,
        ChecklistExecucao.org_id == current_user.org_id,
        ChecklistExecucao.data_execucao >= inicio
    ).all()

    feitos = {ex.data_execucao for ex in execucoes}
    dias = []
    d = inicio
    while d <= hoje:
        dias.append({
            "data": d,
            "feito": d in feitos,
            "fim_semana": d.weekday() >= 5,
        })
        d += timedelta(days=1)

    historico = ChecklistExecucao.query.filter_by(
        equipamento_id=equip_id, org_id=current_user.org_id
    ).order_by(ChecklistExecucao.data_execucao.desc()).limit(30).all()

    return render_template("equipamentos/detalhe.html",
                           equip=e, status=s, dias=dias, historico=historico)


@equipamentos_bp.route("/<int:equip_id>/excluir", methods=["POST"])
@login_required
def excluir(equip_id):
    e = Equipamento.query.filter_by(id=equip_id, org_id=current_user.org_id).first_or_404()
    e.ativo = False
    db.session.commit()
    flash(f"Equipamento '{e.nome}' desativado.", "ok")
    return redirect(url_for("equipamentos.index"))


@equipamentos_bp.route("/templates/")
@login_required
def templates_lista():
    ts = ChecklistTemplate.query.filter_by(org_id=current_user.org_id).all()
    return render_template("equipamentos/templates_lista.html", templates=ts)


@equipamentos_bp.route("/templates/novo", methods=["GET", "POST"])
@login_required
def template_novo():
    if request.method == "POST":
        itens_raw = request.form.get("itens_json", "[]")
        try:
            itens = json.loads(itens_raw)
        except Exception:
            itens = []
        t = ChecklistTemplate(
            org_id=current_user.org_id,
            nome=request.form["nome"],
            itens=itens,
        )
        db.session.add(t)
        db.session.commit()
        flash(f"Template '{t.nome}' criado.", "ok")
        return redirect(url_for("equipamentos.templates_lista"))
    return render_template("equipamentos/template_form.html", template=None)


@equipamentos_bp.route("/templates/<int:tmpl_id>/editar", methods=["GET", "POST"])
@login_required
def template_editar(tmpl_id):
    t = ChecklistTemplate.query.filter_by(id=tmpl_id, org_id=current_user.org_id).first_or_404()
    if request.method == "POST":
        itens_raw = request.form.get("itens_json", "[]")
        try:
            t.itens = json.loads(itens_raw)
        except Exception:
            pass
        t.nome = request.form["nome"]
        db.session.commit()
        flash(f"Template '{t.nome}' atualizado.", "ok")
        return redirect(url_for("equipamentos.templates_lista"))
    return render_template("equipamentos/template_form.html", template=t)


# ── Mobile: preencher checklist (público com org_slug) ──
@equipamentos_bp.route("/m/<int:equip_id>", methods=["GET", "POST"])
def mobile_checklist(equip_id):
    e = Equipamento.query.filter_by(id=equip_id, ativo=True).first_or_404()
    tmpl = e.template

    if request.method == "POST":
        respostas = {}
        for k, v in request.form.items():
            if k.startswith("item_"):
                item_id = k[5:]
                respostas[item_id] = {"valor": v}

        # Verificar se já existe execução hoje
        hoje = date.today()
        existente = ChecklistExecucao.query.filter_by(
            equipamento_id=equip_id,
            org_id=e.org_id,
            data_execucao=hoje
        ).first()

        if existente:
            existente.respostas = respostas
            existente.status = "COMPLETO"
        else:
            ex = ChecklistExecucao(
                org_id=e.org_id,
                equipamento_id=equip_id,
                template_id=tmpl.id if tmpl else None,
                data_execucao=hoje,
                respostas=respostas,
                status="COMPLETO",
                latitude=request.form.get("lat") or None,
                longitude=request.form.get("lon") or None,
            )
            db.session.add(ex)

        db.session.commit()
        return redirect(url_for("equipamentos.mobile_obrigado", equip_id=equip_id))

    return render_template("equipamentos/mobile_checklist.html", equip=e, tmpl=tmpl)


@equipamentos_bp.route("/m/<int:equip_id>/obrigado")
def mobile_obrigado(equip_id):
    e = Equipamento.query.filter_by(id=equip_id, ativo=True).first_or_404()
    return render_template("equipamentos/mobile_obrigado.html", equip=e)


@equipamentos_bp.route("/api/<int:equip_id>/status")
@login_required
def api_status(equip_id):
    Equipamento.query.filter_by(id=equip_id, org_id=current_user.org_id).first_or_404()
    s = _calcular_status(equip_id, current_user.org_id)
    return jsonify({**s, "ultima": s["ultima"].isoformat() if s["ultima"] else None})
