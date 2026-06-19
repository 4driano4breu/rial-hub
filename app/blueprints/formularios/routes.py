import csv
import io
import json
import unicodedata

from flask import (
    render_template, request, redirect, url_for, flash, Response, abort
)
from flask_login import login_required, current_user

from app.blueprints.formularios import formularios_bp
from app.extensions import db
from app.models import Organization, FormularioTemplate, FormularioResposta


def _slugify(texto):
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    base = base.lower().strip()
    out = []
    for ch in base:
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "form"


def _slug_unico(org_id, nome, ignorar_id=None):
    base = _slugify(nome)
    slug = base
    i = 2
    while True:
        q = FormularioTemplate.query.filter_by(org_id=org_id, slug=slug)
        if ignorar_id:
            q = q.filter(FormularioTemplate.id != ignorar_id)
        if not q.first():
            return slug
        slug = f"{base}-{i}"
        i += 1


# ── Admin ──

@formularios_bp.route("/")
@login_required
def index():
    templates = FormularioTemplate.query.filter_by(
        org_id=current_user.org_id, ativo=True
    ).order_by(FormularioTemplate.criado_em.desc()).all()
    cards = []
    for t in templates:
        total = FormularioResposta.query.filter_by(
            org_id=current_user.org_id, template_id=t.id
        ).count()
        cards.append({"tpl": t, "respostas": total})
    return render_template("formularios/index.html", cards=cards)


@formularios_bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Informe um nome para o formulário.", "error")
            return render_template("formularios/novo.html")
        try:
            t = FormularioTemplate(
                org_id=current_user.org_id,
                nome=nome,
                descricao=(request.form.get("descricao") or "").strip(),
                slug=_slug_unico(current_user.org_id, nome),
                aceita_anonimo=bool(request.form.get("aceita_anonimo")),
                campos=[],
            )
            db.session.add(t)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao criar formulário.", "error")
            return render_template("formularios/novo.html")
        flash(f"Formulário '{t.nome}' criado. Adicione os campos.", "ok")
        return redirect(url_for("formularios.editar", id=t.id))
    return render_template("formularios/novo.html")


@formularios_bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar(id):
    t = FormularioTemplate.query.filter_by(
        id=id, org_id=current_user.org_id
    ).first_or_404()
    org = Organization.query.get(current_user.org_id)

    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "save":
                nome = (request.form.get("nome") or "").strip()
                if nome:
                    t.nome = nome
                t.descricao = (request.form.get("descricao") or "").strip()
                t.aceita_anonimo = bool(request.form.get("aceita_anonimo"))
                db.session.commit()
                flash("Formulário atualizado.", "ok")

            elif action == "add_campo":
                campos = list(t.campos or [])
                novo_id = "c" + str(max([int(c["id"][1:]) for c in campos if c.get("id", "").startswith("c") and c["id"][1:].isdigit()] + [0]) + 1)
                tipo = request.form.get("tipo", "texto")
                campo = {
                    "id": novo_id,
                    "tipo": tipo,
                    "label": (request.form.get("label") or "").strip() or "Campo",
                    "obrigatorio": bool(request.form.get("obrigatorio")),
                }
                if tipo == "select":
                    opcoes_raw = request.form.get("opcoes", "")
                    campo["opcoes"] = [o.strip() for o in opcoes_raw.split(",") if o.strip()]
                if tipo == "numero":
                    campo["unidade"] = (request.form.get("unidade") or "").strip()
                campos.append(campo)
                t.campos = campos
                db.session.commit()
                flash("Campo adicionado.", "ok")

            elif action == "remove_campo":
                campo_id = request.form.get("campo_id")
                t.campos = [c for c in (t.campos or []) if c.get("id") != campo_id]
                db.session.commit()
                flash("Campo removido.", "ok")
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar alterações.", "error")
        return redirect(url_for("formularios.editar", id=t.id))

    mobile_url = url_for(
        "formularios.form_mobile", org_slug=org.slug, form_slug=t.slug, _external=True
    )
    return render_template("formularios/editar.html", tpl=t, org=org, mobile_url=mobile_url)


@formularios_bp.route("/<int:id>/respostas")
@login_required
def respostas(id):
    t = FormularioTemplate.query.filter_by(
        id=id, org_id=current_user.org_id
    ).first_or_404()
    page = request.args.get("page", 1, type=int)
    pag = FormularioResposta.query.filter_by(
        org_id=current_user.org_id, template_id=t.id
    ).order_by(FormularioResposta.criado_em.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    preview_campos = (t.campos or [])[:3]
    return render_template(
        "formularios/respostas.html", tpl=t, pag=pag, preview_campos=preview_campos
    )


@formularios_bp.route("/<int:id>/exportar")
@login_required
def exportar(id):
    t = FormularioTemplate.query.filter_by(
        id=id, org_id=current_user.org_id
    ).first_or_404()
    campos = t.campos or []

    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["Data envio", "Enviado por"] + [c.get("label", c.get("id")) for c in campos]
    writer.writerow(header)

    respostas = FormularioResposta.query.filter_by(
        org_id=current_user.org_id, template_id=t.id
    ).order_by(FormularioResposta.criado_em.asc()).all()

    for r in respostas:
        dados = r.dados or {}
        linha = [
            r.criado_em.strftime("%d/%m/%Y %H:%M") if r.criado_em else "",
            str(r.enviado_por) if r.enviado_por else "Anônimo",
        ]
        for c in campos:
            linha.append(str(dados.get(c.get("id"), "")))
        writer.writerow(linha)

    csv_bytes = ("﻿" + buf.getvalue()).encode("utf-8")
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{t.slug}-respostas.csv"'
        },
    )


@formularios_bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
def excluir(id):
    t = FormularioTemplate.query.filter_by(
        id=id, org_id=current_user.org_id
    ).first_or_404()
    try:
        t.ativo = False
        db.session.commit()
        flash(f"Formulário '{t.nome}' excluído.", "ok")
    except Exception:
        db.session.rollback()
        flash("Erro ao excluir formulário.", "error")
    return redirect(url_for("formularios.index"))


# ── Público (mobile) ──

@formularios_bp.route("/f/<org_slug>/<form_slug>", methods=["GET", "POST"])
def form_mobile(org_slug, form_slug):
    org = Organization.query.filter_by(slug=org_slug, ativo=True).first()
    if not org:
        return render_template("formularios/form_mobile.html", tpl=None), 404
    t = FormularioTemplate.query.filter_by(
        org_id=org.id, slug=form_slug, ativo=True
    ).first()
    if not t:
        return render_template("formularios/form_mobile.html", tpl=None), 404

    if not t.aceita_anonimo and not current_user.is_authenticated:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        dados = {}
        for c in (t.campos or []):
            cid = c.get("id")
            dados[cid] = request.form.get(cid, "")
        try:
            r = FormularioResposta(
                org_id=org.id,
                template_id=t.id,
                dados=dados,
                enviado_por=current_user.id if current_user.is_authenticated else None,
                latitude=request.form.get("lat") or None,
                longitude=request.form.get("lon") or None,
                dispositivo=request.headers.get("User-Agent", "")[:200],
            )
            db.session.add(r)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao enviar resposta. Tente novamente.", "error")
            return render_template("formularios/form_mobile.html", tpl=t, org=org)
        return redirect(url_for(
            "formularios.form_obrigado", org_slug=org_slug, form_slug=form_slug
        ))

    return render_template("formularios/form_mobile.html", tpl=t, org=org)


@formularios_bp.route("/f/<org_slug>/<form_slug>/obrigado")
def form_obrigado(org_slug, form_slug):
    org = Organization.query.filter_by(slug=org_slug, ativo=True).first()
    if not org:
        abort(404)
    t = FormularioTemplate.query.filter_by(
        org_id=org.id, slug=form_slug, ativo=True
    ).first()
    if not t:
        abort(404)
    return render_template("formularios/obrigado.html", tpl=t, org=org)
