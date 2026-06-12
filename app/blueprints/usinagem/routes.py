import tempfile
from pathlib import Path
from flask import render_template, request, send_from_directory, current_app, flash, redirect, url_for

from app.blueprints.usinagem import usinagem_bp


@usinagem_bp.route("/")
def index():
    return render_template("usinagem/index.html")


def _dashboard(filename: str):
    folder = Path(current_app.static_folder) / "ferramentas" / "usinagem"
    return send_from_directory(folder, filename)


@usinagem_bp.route("/geral")
def geral():
    return _dashboard("geral.html")


@usinagem_bp.route("/aegea")
def aegea():
    return _dashboard("aegea.html")


@usinagem_bp.route("/guariroba")
def guariroba():
    return _dashboard("guariroba.html")


@usinagem_bp.route("/atualizar", methods=["POST"])
def atualizar():
    csv_file = request.files.get("csv")
    if not csv_file or not csv_file.filename.endswith(".csv"):
        flash("Envie um arquivo .csv exportado do Google Sheets.", "error")
        return redirect(url_for("usinagem.index"))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    tmp.write(csv_file.read())
    tmp.close()
    csv_path = Path(tmp.name)

    try:
        from app.blueprints.usinagem import updater as _upd
        import importlib
        importlib.reload(_upd)  # garante paths atualizados

        linhas_raw = _upd.ler_csv(str(csv_path))
        linhas = _upd.deduplicar(linhas_raw)
        aegea     = _upd.ordenar_desc([r for r in linhas if _upd.classificar(r[_upd.COL_REGIAO]) == "AEGEA"])
        guariroba = _upd.ordenar_desc([r for r in linhas if _upd.classificar(r[_upd.COL_REGIAO]) == "GUARIROBA"])
        todas     = _upd.ordenar_desc(linhas)

        _upd.atualizar_aegea(aegea)
        _upd.atualizar_guariroba(guariroba)
        _upd.atualizar_geral(todas)

        flash(f"Dashboards atualizados: {len(todas)} registros totais (AEGEA: {len(aegea)}, Guariroba: {len(guariroba)}).", "ok")
    except Exception as e:
        flash(f"Erro ao processar CSV: {e}", "error")
    finally:
        csv_path.unlink(missing_ok=True)

    return redirect(url_for("usinagem.index"))
