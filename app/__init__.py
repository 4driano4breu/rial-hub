import click
import os
from pathlib import Path
from flask import Flask, render_template, redirect, url_for
from flask_login import current_user

from werkzeug.middleware.proxy_fix import ProxyFix
from app.extensions import db, migrate, login_manager, bcrypt, csrf, limiter, talisman

# CSP compatível com todos os dashboards atuais (cdnjs, unpkg, Google Fonts)
# 'unsafe-inline' e 'unsafe-eval' necessários para as ferramentas legadas (PDF.js, xlsx.js)
# Serão removidos na Fase 2.0 quando os dashboards forem reconstruídos
_CSP = {
    'default-src': "'self'",
    'script-src':  ["'self'", "'unsafe-inline'", "'unsafe-eval'", "blob:",
                    "cdnjs.cloudflare.com", "unpkg.com"],
    'style-src':   ["'self'", "'unsafe-inline'",
                    "cdnjs.cloudflare.com", "fonts.googleapis.com"],
    'font-src':    ["'self'", "fonts.gstatic.com", "cdnjs.cloudflare.com", "data:"],
    'img-src':     ["'self'", "data:", "blob:"],
    'worker-src':  ["'self'", "blob:"],
    'connect-src': ["'self'", "blob:"],
    'object-src':  "'none'",
    'base-uri':    "'self'",
    'frame-ancestors': "'none'",
}


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

    # Railway termina HTTPS no proxy — ProxyFix repassa o esquema correto ao Flask
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Inicializar extensões
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    _prod = os.environ.get("FLASK_ENV") == "production"
    talisman.init_app(
        app,
        force_https=False,                          # Railway já força HTTPS no edge
        strict_transport_security=_prod,
        strict_transport_security_max_age=31536000,
        strict_transport_security_include_subdomains=True,
        content_security_policy=_CSP,
        referrer_policy="strict-origin-when-cross-origin",
        frame_options="DENY",
    )

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
    from app.blueprints.equipamentos import equipamentos_bp

    from app.blueprints.admin import admin_bp
    from app.blueprints.dados import dados_bp
    from app.blueprints.formularios import formularios_bp

    app.register_blueprint(notas_bp,        url_prefix="/notas")
    app.register_blueprint(faturamento_bp,  url_prefix="/faturamento")
    app.register_blueprint(usinagem_bp,     url_prefix="/usinagem")
    app.register_blueprint(ferramentas_bp,  url_prefix="/ferramentas")
    app.register_blueprint(equipamentos_bp, url_prefix="/equipamentos")
    app.register_blueprint(admin_bp,        url_prefix="/admin")
    app.register_blueprint(dados_bp)
    app.register_blueprint(formularios_bp)

    @app.route("/")
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        return render_template("index.html")

    @app.route("/landing")
    def landing():
        return render_template("landing.html")

    # Proteger todas as rotas exceto auth e static
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.before_request
    def require_login():
        from flask import request
        public = {"auth.login", "auth.logout", "static", "landing",
                  "equipamentos.mobile_checklist", "equipamentos.mobile_obrigado",
                  "formularios.form_mobile", "formularios.form_obrigado"}
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

    from app.org_settings import _DEFAULTS
    rial = Organization(slug="rial", name="RIAL Construtora", plan="pro",
                        settings=_DEFAULTS)
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
    _seed_template_retro(rial.id)
    click.echo(f"✓ Organização '{rial.name}' e usuário '{admin_email}' criados.")


@click.command("seed-auto")
def _seed_auto_command():
    """Seed automático via variáveis de ambiente ADMIN_EMAIL e ADMIN_PASSWORD."""
    from app.extensions import bcrypt
    from app.models import Organization, User

    if Organization.query.first():
        click.echo("Seed-auto: banco já possui dados, pulando.")
        return

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@rial.com.br").strip()
    admin_senha = os.environ.get("ADMIN_PASSWORD", "").strip()
    admin_nome  = os.environ.get("ADMIN_NOME", "Administrador RIAL").strip()

    if not admin_senha:
        click.echo("ERRO: variável ADMIN_PASSWORD não definida. Seed abortado.")
        raise SystemExit(1)

    from app.org_settings import _DEFAULTS
    rial = Organization(slug="rial", name="RIAL Construtora", plan="pro",
                        settings=_DEFAULTS)
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
    _seed_template_retro(rial.id)
    click.echo(f"✓ Seed-auto: organização 'RIAL Construtora' e usuário '{admin_email}' criados.")


def _seed_template_retro(org_id):
    """Cria o template de checklist da Retroescavadeira JCB 3CX se não existir."""
    from app.models import ChecklistTemplate

    if ChecklistTemplate.query.filter_by(org_id=org_id).first():
        return

    tmpl = ChecklistTemplate(org_id=org_id, nome="Retroescavadeira JCB 3CX", itens=[
        {"id": "oleo_motor", "categoria": "Fluidos", "descricao": "Nível de óleo do motor", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "fluido_hidra", "categoria": "Fluidos", "descricao": "Nível do fluido hidráulico", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "combustivel", "categoria": "Fluidos", "descricao": "Nível de combustível (%)", "tipo": "numero", "obrigatorio": True, "unidade": "%"},
        {"id": "agua_radiador", "categoria": "Fluidos", "descricao": "Nível da água do radiador", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "pressao_diant", "categoria": "Pneus", "descricao": "Pressão dianteira esq./dir. (bar)", "tipo": "numero", "obrigatorio": False, "unidade": "bar"},
        {"id": "pressao_tras", "categoria": "Pneus", "descricao": "Pressão traseira esq./dir. (bar)", "tipo": "numero", "obrigatorio": False, "unidade": "bar"},
        {"id": "freios", "categoria": "Segurança", "descricao": "Freios funcionando", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "sinal_re", "categoria": "Segurança", "descricao": "Sinal sonoro de ré", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "extintor", "categoria": "Segurança", "descricao": "Extintor de incêndio", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "cinto", "categoria": "Segurança", "descricao": "Cinto de segurança", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "farois", "categoria": "Iluminação", "descricao": "Faróis dianteiros", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "luz_re", "categoria": "Iluminação", "descricao": "Luz de ré", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "vazamentos", "categoria": "Visual", "descricao": "Vazamentos visíveis", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "cacamba", "categoria": "Visual", "descricao": "Condição da caçamba", "tipo": "ok_nao_ok", "obrigatorio": False},
        {"id": "espelhos", "categoria": "Visual", "descricao": "Espelhos retrovisores", "tipo": "ok_nao_ok", "obrigatorio": True},
        {"id": "foto_geral", "categoria": "Registro", "descricao": "Foto geral da máquina", "tipo": "foto", "obrigatorio": False},
        {"id": "obs", "categoria": "Registro", "descricao": "Observações do operador", "tipo": "texto", "obrigatorio": False},
    ])
    db.session.add(tmpl)
    db.session.commit()


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
