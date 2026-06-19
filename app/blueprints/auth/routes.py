from datetime import datetime
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required

from app.blueprints.auth import auth_bp
from app.blueprints.auth.forms import LoginForm
from app.extensions import bcrypt, db
from app.models import User, InviteToken


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.ativo and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        flash("E-mail ou senha incorretos.", "error")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha  = request.form.get("nova_senha", "").strip()
        confirma    = request.form.get("confirma", "").strip()

        if not bcrypt.check_password_hash(current_user.password_hash, senha_atual):
            flash("Senha atual incorreta.", "error")
        elif len(nova_senha) < 8:
            flash("Nova senha deve ter ao menos 8 caracteres.", "error")
        elif nova_senha != confirma:
            flash("As senhas não conferem.", "error")
        else:
            current_user.password_hash = bcrypt.generate_password_hash(
                nova_senha, rounds=12
            ).decode("utf-8")
            db.session.commit()
            flash("Senha alterada com sucesso.", "ok")
            return redirect(url_for("auth.perfil"))

    return render_template("auth/perfil.html")


@auth_bp.route("/convite/<token>", methods=["GET", "POST"])
def aceitar_convite(token):
    convite = InviteToken.query.filter_by(token=token, usado=False).first_or_404()
    if convite.expires_at < datetime.utcnow():
        flash("Este link de convite expirou. Solicite um novo ao administrador.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        nome     = request.form.get("nome", "").strip()
        senha    = request.form.get("senha", "").strip()
        confirma = request.form.get("confirma", "").strip()

        erros = []
        if not nome:
            erros.append("Nome obrigatório.")
        if len(senha) < 8:
            erros.append("Senha deve ter ao menos 8 caracteres.")
        if senha != confirma:
            erros.append("Senhas não conferem.")
        if User.query.filter_by(email=convite.email).first():
            erros.append("Este e-mail já tem uma conta.")

        if erros:
            for e in erros:
                flash(e, "error")
            return render_template("auth/convite.html", convite=convite)

        novo = User(
            org_id=convite.org_id,
            email=convite.email,
            nome=nome,
            role=convite.role,
            password_hash=bcrypt.generate_password_hash(senha, rounds=12).decode("utf-8"),
            ativo=True,
        )
        db.session.add(novo)
        convite.usado = True
        db.session.commit()
        login_user(novo)
        flash(f"Bem-vindo(a), {nome}! Sua conta foi criada.", "ok")
        return redirect(url_for("index"))

    return render_template("auth/convite.html", convite=convite)
