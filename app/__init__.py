from pathlib import Path
from flask import Flask, render_template


def create_app() -> Flask:
    base = Path(__file__).parent.parent
    app = Flask(
        __name__,
        template_folder=str(base / "templates"),
        static_folder=str(base / "static"),
    )
    app.config.from_object("app.config.Config")

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
        return render_template("index.html")

    return app
