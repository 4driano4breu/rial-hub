from functools import wraps
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user, login_required

from app.blueprints.admin import admin_bp
from app.extensions import db, bcrypt
from app.models import Organization, User, InviteToken


def _require_admin(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.has_role("ADMIN", "SUPERADMIN"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _require_superadmin(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.has_role("SUPERADMIN"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Visão geral ───────────────────────────────────────────────────────────────

@admin_bp.route("/")
@_require_admin
def index():
    org = Organization.query.get(current_user.org_id)
    usuarios = User.query.filter_by(org_id=current_user.org_id).order_by(User.criado_em).all()
    return render_template("admin/index.html", org=org, usuarios=usuarios)


# ── Gestão de usuários ────────────────────────────────────────────────────────

@admin_bp.route("/usuarios")
@_require_admin
def usuarios():
    lista = User.query.filter_by(org_id=current_user.org_id).order_by(User.nome).all()
    return render_template("admin/usuarios.html", usuarios=lista)


@admin_bp.route("/usuarios/novo", methods=["GET", "POST"])
@_require_admin
def usuario_novo():
    roles_disponiveis = ["VIEWER", "OPERACIONAL", "FINANCEIRO", "ADMIN"]
    if current_user.has_role("SUPERADMIN"):
        roles_disponiveis.append("SUPERADMIN")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        nome  = request.form.get("nome", "").strip()
        role  = request.form.get("role", "VIEWER")
        senha = request.form.get("senha", "").strip()

        erros = []
        if not email or "@" not in email:
            erros.append("E-mail inválido.")
        if not nome:
            erros.append("Nome obrigatório.")
        if role not in roles_disponiveis:
            erros.append("Cargo inválido.")
        if len(senha) < 8:
            erros.append("Senha deve ter ao menos 8 caracteres.")
        if User.query.filter_by(email=email).first():
            erros.append("E-mail já cadastrado.")

        if erros:
            for e in erros:
                flash(e, "error")
            return render_template("admin/usuario_form.html",
                                   titulo="Novo Usuário", roles=roles_disponiveis,
                                   form=request.form)

        novo = User(
            org_id=current_user.org_id,
            email=email,
            nome=nome,
            role=role,
            password_hash=bcrypt.generate_password_hash(senha, rounds=12).decode("utf-8"),
            ativo=True,
        )
        db.session.add(novo)
        db.session.commit()
        flash(f"Usuário {nome} criado com sucesso.", "ok")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html",
                           titulo="Novo Usuário", roles=roles_disponiveis, form={})


@admin_bp.route("/usuarios/<int:uid>/editar", methods=["GET", "POST"])
@_require_admin
def usuario_editar(uid):
    usuario = User.query.filter_by(id=uid, org_id=current_user.org_id).first_or_404()

    roles_disponiveis = ["VIEWER", "OPERACIONAL", "FINANCEIRO", "ADMIN"]
    if current_user.has_role("SUPERADMIN"):
        roles_disponiveis.append("SUPERADMIN")

    if request.method == "POST":
        nome  = request.form.get("nome", "").strip()
        role  = request.form.get("role", usuario.role)
        ativo = request.form.get("ativo") == "1"
        nova_senha = request.form.get("senha", "").strip()

        if not nome:
            flash("Nome obrigatório.", "error")
            return render_template("admin/usuario_form.html",
                                   titulo="Editar Usuário", usuario=usuario,
                                   roles=roles_disponiveis, form=request.form)

        if role not in roles_disponiveis:
            flash("Cargo inválido.", "error")
            return render_template("admin/usuario_form.html",
                                   titulo="Editar Usuário", usuario=usuario,
                                   roles=roles_disponiveis, form=request.form)

        # Impede admin de se auto-desativar ou rebaixar
        if usuario.id == current_user.id:
            ativo = True
            role = current_user.role

        usuario.nome  = nome
        usuario.role  = role
        usuario.ativo = ativo

        if nova_senha and len(nova_senha) >= 8:
            usuario.password_hash = bcrypt.generate_password_hash(
                nova_senha, rounds=12
            ).decode("utf-8")
        elif nova_senha:
            flash("Nova senha ignorada — mínimo 8 caracteres.", "error")

        db.session.commit()
        flash(f"Usuário {usuario.nome} atualizado.", "ok")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/usuario_form.html",
                           titulo="Editar Usuário", usuario=usuario,
                           roles=roles_disponiveis, form={})


# ── Gestão de organizações (SUPERADMIN) ──────────────────────────────────────

@admin_bp.route("/organizacoes")
@_require_superadmin
def organizacoes():
    orgs = Organization.query.order_by(Organization.criado_em.desc()).all()
    return render_template("admin/organizacoes.html", orgs=orgs)


# ── Convite por link tokenizado ──────────────────────────────────────────────

@admin_bp.route("/convidar", methods=["GET", "POST"])
@_require_admin
def convidar():
    roles_disponiveis = ["VIEWER", "OPERACIONAL", "FINANCEIRO", "ADMIN"]
    convites_recentes = (InviteToken.query
        .filter_by(org_id=current_user.org_id, usado=False)
        .filter(InviteToken.expires_at > datetime.utcnow())
        .order_by(InviteToken.criado_em.desc())
        .limit(10).all())

    link_gerado = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        role  = request.form.get("role", "VIEWER")

        if not email or "@" not in email:
            flash("E-mail inválido.", "error")
        elif role not in roles_disponiveis:
            flash("Cargo inválido.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Esse e-mail já tem uma conta.", "error")
        else:
            convite = InviteToken(
                org_id=current_user.org_id,
                email=email,
                role=role,
                expires_at=datetime.utcnow() + timedelta(hours=48),
                criado_por=current_user.id,
            )
            db.session.add(convite)
            db.session.commit()
            link_gerado = request.host_url.rstrip("/") + url_for("auth.aceitar_convite", token=convite.token)
            flash("Convite gerado! Copie o link abaixo e envie ao convidado.", "ok")

    return render_template("admin/convidar.html",
                           roles=roles_disponiveis,
                           convites=convites_recentes,
                           link_gerado=link_gerado)
