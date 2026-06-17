"""
Fase 2.3 — Onboarding wizard (3 passos) para criar nova organização (SUPERADMIN).
"""
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import current_user, login_required
from functools import wraps

from app.blueprints.admin import admin_bp
from app.extensions import db, bcrypt
from app.models import Organization, User
from app.org_settings import _DEFAULTS


def _require_superadmin(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.has_role("SUPERADMIN"):
            flash("Acesso restrito a SUPERADMIN.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/onboarding", methods=["GET", "POST"])
@_require_superadmin
def onboarding():
    """Passo 1 — Dados da empresa."""
    if request.method == "POST":
        nome  = request.form.get("nome", "").strip()
        slug  = request.form.get("slug", "").strip().lower()
        plano = request.form.get("plano", "starter")

        erros = []
        if not nome:
            erros.append("Nome da empresa obrigatório.")
        if not slug or not slug.isidentifier():
            erros.append("Slug inválido — use apenas letras, números e underscore.")
        if Organization.query.filter_by(slug=slug).first():
            erros.append(f"Slug '{slug}' já está em uso.")

        if erros:
            for e in erros:
                flash(e, "error")
            return render_template("admin/onboarding_passo1.html", form=request.form)

        session["onb"] = {"nome": nome, "slug": slug, "plano": plano}
        return redirect(url_for("admin.onboarding_passo2"))

    return render_template("admin/onboarding_passo1.html", form={})


@admin_bp.route("/onboarding/passo2", methods=["GET", "POST"])
@_require_superadmin
def onboarding_passo2():
    """Passo 2 — Configuração do contrato (alíquotas, CAP)."""
    if "onb" not in session:
        return redirect(url_for("admin.onboarding"))

    defaults = _DEFAULTS
    if request.method == "POST":
        try:
            aliquotas = {
                "pav":      float(request.form.get("aliq_pav", 0.10)),
                "canteiro": float(request.form.get("aliq_canteiro", 0.35)),
                "rocada":   float(request.form.get("aliq_rocada", 0.35)),
                "terra":    float(request.form.get("aliq_terra", 0.15)),
                "inss":     float(request.form.get("aliq_inss", 0.11)),
            }
            usinagem = {
                "cap_aegea":      float(request.form.get("cap_aegea", 30.0)),
                "cap_guariroba":  float(request.form.get("cap_guariroba", 63.93)),
                "composicao_cap": float(request.form.get("composicao_cap", 0.051)),
            }
        except ValueError:
            flash("Valores numéricos inválidos.", "error")
            return render_template("admin/onboarding_passo2.html", defaults=defaults)

        session["onb"]["settings"] = {"aliquotas": aliquotas, "usinagem": usinagem}
        return redirect(url_for("admin.onboarding_passo3"))

    return render_template("admin/onboarding_passo2.html", defaults=defaults)


@admin_bp.route("/onboarding/passo3", methods=["GET", "POST"])
@_require_superadmin
def onboarding_passo3():
    """Passo 3 — Usuário administrador da org."""
    if "onb" not in session or "settings" not in session.get("onb", {}):
        return redirect(url_for("admin.onboarding"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        nome  = request.form.get("nome", "").strip()
        senha = request.form.get("senha", "").strip()

        erros = []
        if not email or "@" not in email:
            erros.append("E-mail inválido.")
        if not nome:
            erros.append("Nome obrigatório.")
        if len(senha) < 8:
            erros.append("Senha mínima: 8 caracteres.")
        if User.query.filter_by(email=email).first():
            erros.append("E-mail já cadastrado.")

        if erros:
            for e in erros:
                flash(e, "error")
            return render_template("admin/onboarding_passo3.html", form=request.form)

        onb = session.pop("onb")
        org = Organization(
            slug=onb["slug"],
            name=onb["nome"],
            plan=onb["plano"],
            settings=onb["settings"],
            ativo=True,
        )
        db.session.add(org)
        db.session.flush()

        admin = User(
            org_id=org.id,
            email=email,
            nome=nome,
            role="ADMIN",
            password_hash=bcrypt.generate_password_hash(senha, rounds=12).decode("utf-8"),
            ativo=True,
        )
        db.session.add(admin)
        db.session.commit()

        flash(f"Organização '{org.name}' criada com sucesso. Usuário admin: {email}", "ok")
        return redirect(url_for("admin.organizacoes"))

    return render_template("admin/onboarding_passo3.html", form={})
