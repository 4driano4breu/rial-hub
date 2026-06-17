import click
import os
from pathlib import Path
from flask import Flask, render_template, redirect, url_for
from flask_login import current_user

from app.extensions import db, migrate, login_manager, bcrypt, csrf, limiter


def create_app() -> Flask:
    base = Path(__file__).parent.parent
    app = Flask(
        __name__,
        template_folder=str(base / "templates"),
        static_folder=str(base / "static"),
    )
    app.config.from_object("app.config.Config")

    # Garantir pasta instance/ para SQLite local
    (base / "instance").mkdir(exist_ok=True)

    # Inicializar extensões
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faça login para acessar esta página."
    login_manager.login_message_category = "error"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # Rate limiting em login
    from app.blueprints.auth import auth_bp
    limiter.limit("10 per hour")(auth_bp)

    # Blueprints — auth (público)
    app.register_blueprint(auth_bp, url_prefix="/auth")

    # Blueprints — módulos (protegidos via @login_required em cada rota)
    from app.blueprints.notas import notas_bp
    from app.blueprints.faturamento import faturamento_bp
    from app.blueprints.usinagem import usinagem_bp
    from app.blueprints.ferramentas import ferramentas_bp

    app.register_blueprint(notas_bp,       url_prefix="/notas")
    app.register_blueprint(faturamento_bp, url_prefix="/faturamento")
    app.register_blueprint(usinagem_bp,    url_prefix="/usinagem")
    app.register_blueprint(ferramentas_bp, url_prefix="/ferramentas")

    @app.route("/")
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        return render_template("index.html")

    # Proteger todas as rotas exceto auth e static
    @app.before_request
    def require_login():
        from flask import request
        public = {"auth.login", "auth.logout", "static"}
        if request.endpoint and request.endpoint not in public:
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))

    # Comandos CLI
    app.cli.add_command(_seed_command)
    app.cli.add_command(_seed_auto_command)
    app.cli.add_command(_r2_pull_command)

    return app


@click.command("seed")
def _seed_command():
    """Cria organização RIAL e usuário admin interativamente."""
    from app.extensions import bcrypt
    from app.models import Organization, User

    if Organization.query.first():
        click.echo("Banco já possui dados. Seed ignorado.")
        return

    rial = Organization(slug="rial", name="RIAL Construtora", plan="pro")
    db.session.add(rial)
    db.session.flush()

    admin_email = click.prompt("E-mail do admin", default="admin@rial.com.br")
    admin_nome  = click.prompt("Nome do admin",  default="Administrador RIAL")
    admin_senha = click.prompt("Senha do admin", hide_input=True, confirmation_prompt=True)

    admin = User(
        org_id        = rial.id,
        email         = admin_email.lower(),
        nome          = admin_nome,
        password_hash = bcrypt.generate_password_hash(admin_senha, rounds=12).decode("utf-8"),
        role          = "ADMIN",
    )
    db.session.add(admin)
    db.session.commit()
    click.echo(f"✓ Organização '{rial.name}' e usuário '{admin_email}' criados.")


@click.command("seed-auto")
def _seed_auto_command():
    """Seed automático via variáveis de ambiente ADMIN_EMAIL e ADMIN_PASSWORD."""
    from app.extensions import bcrypt
    from app.models import Organization, User

    if Organization.query.first():
        click.echo("Seed-auto: banco já possui dados, pulando.")
        return

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@rial.com.br")
    admin_senha = os.environ.get("ADMIN_PASSWORD")
    admin_nome  = os.environ.get("ADMIN_NOME", "Administrador RIAL")

    if not admin_senha:
        click.echo("ERRO: variável ADMIN_PASSWORD não definida. Seed abortado.")
        raise SystemExit(1)

    rial = Organization(slug="rial", name="RIAL Construtora", plan="pro")
    db.session.add(rial)
    db.session.flush()

    admin = User(
        org_id        = rial.id,
        email         = admin_email.lower(),
        nome          = admin_nome,
        password_hash = bcrypt.generate_password_hash(admin_senha, rounds=12).decode("utf-8"),
        role          = "ADMIN",
    )
    db.session.add(admin)
    db.session.commit()
    click.echo(f"✓ Seed-auto: organização 'RIAL Construtora' e usuário '{admin_email}' criados.")


@click.command("r2-pull")
def _r2_pull_command():
    """Restaura arquivos do Cloudflare R2 para o filesystem local (idempotente)."""
    from pathlib import Path
    from flask import current_app
    import app.storage as r2

    if not r2._ready():
        click.echo("R2-pull: R2 não configurado — pulando.")
        return

    static = Path(current_app.static_folder)
    instance_faturamento = Path(current_app.instance_path) / "faturamento"
    instance_faturamento.mkdir(parents=True, exist_ok=True)

    targets = {
        "usinagem/geral.html":              static / "ferramentas" / "usinagem" / "geral.html",
        "usinagem/aegea.html":              static / "ferramentas" / "usinagem" / "aegea.html",
        "usinagem/guariroba.html":          static / "ferramentas" / "usinagem" / "guariroba.html",
        "faturamento/dashboard.html":       static / "ferramentas" / "faturamento" / "dashboard.html",
        "faturamento/Faturamento_2026.xlsx": instance_faturamento / "Faturamento 2026.xlsx",
    }

    pulled = 0
    for key, local_path in targets.items():
        data = r2.download(key)
        if data:
            local_path.write_bytes(data)
            pulled += 1
            click.echo(f"  ✓ {key}")

    click.echo(f"R2-pull: {pulled}/{len(targets)} arquivo(s) restaurado(s).")
