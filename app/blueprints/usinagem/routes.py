import csv
import io
import tempfile
from datetime import date, datetime
from pathlib import Path
from flask import render_template, request, send_from_directory, current_app, flash, redirect, url_for, jsonify, Response
from flask_login import current_user, login_required

from app.blueprints.usinagem import usinagem_bp
from app.extensions import db
from app.models import UsinagemRegistro
from app.org_settings import get_usinagem_cfg

_R2_FILES = {
    "geral":      "usinagem/geral.html",
    "aegea":      "usinagem/aegea.html",
    "guariroba":  "usinagem/guariroba.html",
}


def _dashboard_folder() -> Path:
    return Path(current_app.static_folder) / "ferramentas" / "usinagem"


def _dashboard(name: str):
    """Serve dashboard: tenta R2 primeiro (persiste entre deploys), fallback para static local."""
    import app.storage as r2
    r2_key = _R2_FILES.get(name)
    if r2_key:
        data = r2.download(r2_key)
        if data:
            return Response(data, content_type="text/html; charset=utf-8")
    return send_from_directory(_dashboard_folder(), f"{name}.html")


def _xlsx_to_csv_path(xlsx_bytes: bytes) -> str:
    """Converte XLSX em CSV temporário e retorna o caminho."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb.active
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w",
                                      encoding="utf-8-sig", newline="")
    writer = csv.writer(tmp)
    for row in ws.iter_rows(values_only=True):
        writer.writerow(["" if v is None else str(v) for v in row])
    tmp.close()
    return tmp.name


def _parse_data(val: str):
    """Tenta converter string de data em date. Aceita dd/mm/yyyy e yyyy-mm-dd."""
    if not val:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            pass
    return None


def _salvar_registros_db(linhas: list[dict], org_id: int) -> int:
    """Persiste lista de dicts (com chaves mapeadas) em UsinagemRegistro. Retorna nº de novos."""
    novos = 0
    for r in linhas:
        ticket = str(r.get("ticket") or "").strip()
        if not ticket:
            continue
        if UsinagemRegistro.query.filter_by(org_id=org_id, ticket=ticket).first():
            continue
        reg = UsinagemRegistro(
            org_id=org_id,
            ticket=ticket,
            data_operacao=_parse_data(str(r.get("data") or "")),
            placa=str(r.get("placa") or ""),
            motorista=str(r.get("motorista") or ""),
            peso_bruto=_to_float(r.get("peso_bruto")),
            tara=_to_float(r.get("tara")),
            peso_liquido=_to_float(r.get("peso_liquido")),
            regiao=str(r.get("regiao") or ""),
            contrato=str(r.get("contrato") or ""),
        )
        db.session.add(reg)
        novos += 1
    db.session.commit()
    return novos


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None


@usinagem_bp.route("/")
def index():
    from core.timestamps import ler_timestamps
    ts = ler_timestamps()
    org_id = current_user.org_id if current_user.is_authenticated else 1
    total_db = UsinagemRegistro.query.filter_by(org_id=org_id).count()
    sheets_ok = bool(__import__("os").environ.get("GOOGLE_CREDENTIALS_JSON"))
    org = current_user.organization if current_user.is_authenticated else None
    sheets_cfg = (org.settings or {}).get("usinagem", {}) if org else {}
    spreadsheet_id = sheets_cfg.get("spreadsheet_id", "")
    return render_template(
        "usinagem/index.html",
        ultima_atualizacao=ts.get("usinagem", "—"),
        total_db=total_db,
        sheets_ok=sheets_ok,
        spreadsheet_id=spreadsheet_id,
    )


@usinagem_bp.route("/geral")
def geral():
    return _dashboard("geral")


@usinagem_bp.route("/aegea")
def aegea():
    return _dashboard("aegea")


@usinagem_bp.route("/guariroba")
def guariroba():
    return _dashboard("guariroba")


@login_required
@usinagem_bp.route("/sincronizar", methods=["POST"])
def sincronizar():
    """Sincroniza do Google Sheets para UsinagemRegistro no banco."""
    from app.services import sheets as _sheets

    if not __import__("os").environ.get("GOOGLE_CREDENTIALS_JSON"):
        flash("Google Sheets não configurado. Defina GOOGLE_CREDENTIALS_JSON nas variáveis de ambiente.", "error")
        return redirect(url_for("usinagem.index"))

    org = current_user.organization
    sheets_cfg = (org.settings or {}).get("usinagem", {})
    spreadsheet_id = sheets_cfg.get("spreadsheet_id", "")
    sheet_range    = sheets_cfg.get("sheet_range", "Sheet1")

    if not spreadsheet_id:
        flash("ID da planilha não configurado. Adicione 'spreadsheet_id' em Configurações da organização.", "error")
        return redirect(url_for("usinagem.index"))

    try:
        rows = _sheets.ler_planilha(spreadsheet_id, sheet_range)
        if not rows:
            flash("Nenhum dado retornado da planilha. Verifique o ID e as permissões.", "error")
            return redirect(url_for("usinagem.index"))

        # Normaliza chaves do dict para o padrão interno
        mapa = sheets_cfg.get("col_map", {
            "ticket":      "Ticket",
            "data":        "Data Operação",
            "placa":       "Placa",
            "motorista":   "Motorista",
            "peso_bruto":  "Tara",
            "peso_liquido":"Peso",
            "regiao":      "Região",
            "contrato":    "Contrato",
        })
        linhas = []
        for row in rows:
            linhas.append({k: row.get(v, "") for k, v in mapa.items()})

        novos = _salvar_registros_db(linhas, current_user.org_id)

        from core.timestamps import salvar_timestamp
        salvar_timestamp("usinagem")
        flash(f"Sincronização concluída: {novos} novos registros de {len(rows)} linhas da planilha.", "ok")
    except Exception as e:
        flash(f"Erro ao sincronizar com Google Sheets: {e}", "error")

    return redirect(url_for("usinagem.index"))


@login_required
@usinagem_bp.route("/atualizar", methods=["POST"])
def atualizar():
    import app.storage as r2

    upload_file = request.files.get("csv")
    if not upload_file or not upload_file.filename:
        flash("Selecione um arquivo .csv ou .xlsx.", "error")
        return redirect(url_for("usinagem.index"))

    fname = upload_file.filename.lower()
    raw = upload_file.read()

    if fname.endswith(".xlsx"):
        try:
            csv_path = Path(_xlsx_to_csv_path(raw))
        except Exception as e:
            flash(f"Erro ao converter XLSX: {e}", "error")
            return redirect(url_for("usinagem.index"))
    elif fname.endswith(".csv"):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        tmp.write(raw)
        tmp.close()
        csv_path = Path(tmp.name)
    else:
        flash("Formato inválido. Envie um arquivo .csv ou .xlsx.", "error")
        return redirect(url_for("usinagem.index"))

    try:
        from app.blueprints.usinagem import updater as _upd
        import importlib
        importlib.reload(_upd)

        linhas_raw = _upd.ler_csv(str(csv_path))
        linhas = _upd.deduplicar(linhas_raw)
        aegea     = _upd.ordenar_desc([r for r in linhas if _upd.classificar(r[_upd.COL_REGIAO]) == "AEGEA"])
        guariroba = _upd.ordenar_desc([r for r in linhas if _upd.classificar(r[_upd.COL_REGIAO]) == "GUARIROBA"])
        todas     = _upd.ordenar_desc(linhas)

        _upd.atualizar_aegea(aegea)
        _upd.atualizar_guariroba(guariroba)
        _upd.atualizar_geral(todas)

        from core.timestamps import salvar_timestamp
        salvar_timestamp("usinagem")

        # Persiste dashboards no R2 (ignorado se R2 não configurado ou sem permissão)
        r2_ok = True
        folder = _dashboard_folder()
        for name, r2_key in _R2_FILES.items():
            local = folder / f"{name}.html"
            if local.exists():
                try:
                    r2.upload(r2_key, local.read_bytes(), "text/html; charset=utf-8")
                except Exception:
                    r2_ok = False

        # Persiste registros no banco também
        try:
            org_id = current_user.org_id if current_user.is_authenticated else 1
            linhas_db = []
            for r in linhas:
                linhas_db.append({
                    "ticket":      str(r[_upd.COL_NOTA]).strip() if len(r) > _upd.COL_NOTA else "",
                    "data":        str(r[_upd.COL_DATA]).strip() if len(r) > _upd.COL_DATA else "",
                    "placa":       str(r[_upd.COL_PLACA]).strip() if len(r) > _upd.COL_PLACA else "",
                    "motorista":   str(r[_upd.COL_MOT]).strip() if len(r) > _upd.COL_MOT else "",
                    "peso_bruto":  str(r[_upd.COL_BRUTO]).strip() if len(r) > _upd.COL_BRUTO else "",
                    "peso_liquido":str(r[_upd.COL_LIQ]).strip() if len(r) > _upd.COL_LIQ else "",
                    "regiao":      str(r[_upd.COL_REGIAO]).strip() if len(r) > _upd.COL_REGIAO else "",
                    "contrato":    "",
                })
            novos = _salvar_registros_db(linhas_db, org_id)
            r2_aviso = "" if r2_ok else " ⚠ R2 indisponível — dashboards ativos até próximo redeploy."
            flash(f"Dashboards atualizados: {len(todas)} registros (AEGEA: {len(aegea)}, Guariroba: {len(guariroba)}). {novos} novos no banco.{r2_aviso}", "ok")
        except Exception as db_err:
            flash(f"Dashboards atualizados, mas erro ao salvar no banco: {db_err}", "error")
    except Exception as e:
        flash(f"Erro ao processar CSV: {e}", "error")
    finally:
        csv_path.unlink(missing_ok=True)

    return redirect(url_for("usinagem.index"))
