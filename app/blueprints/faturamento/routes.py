import io
import json
import tempfile
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from flask import render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import current_user, login_required

import app.storage as r2
from app.blueprints.faturamento import faturamento_bp
from app.extensions import db

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_R2_WARN = " ⚠ R2 indisponível — dados ativos até próximo redeploy."

_R2_XLSX = "faturamento/Faturamento_2026.xlsx"

_MESES_PT = {1:"JANEIRO",2:"FEVEREIRO",3:"MARÇO",4:"ABRIL",5:"MAIO",6:"JUNHO",
             7:"JULHO",8:"AGOSTO",9:"SETEMBRO",10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"}
_MESES_ORDER = list(_MESES_PT.values())


def _xlsx_path() -> Path:
    d = Path(current_app.instance_path) / "faturamento"
    d.mkdir(parents=True, exist_ok=True)
    return d / "Faturamento 2026.xlsx"


def _build_dashboard_data(org_id: int):
    from app.models import FaturamentoNota
    notas = (FaturamentoNota.query
             .filter_by(org_id=org_id, excluido=False)
             .order_by(FaturamentoNota.emissao.asc(), FaturamentoNota.nr.asc())
             .all())

    notes_list = []
    for n in notas:
        notes_list.append({
            "mes": _MESES_PT[n.emissao.month],
            "nr": n.nr,
            "emissao": n.emissao.strftime("%d/%m/%Y"),
            "contrato": n.contrato or "",
            "orgao": n.orgao or "",
            "municipio": n.municipio or "",
            "tipo": n.tipo or "",
            "bruto": float(n.bruto or 0),
            "inss": float(n.inss or 0),
            "ir": float(n.ir or 0),
            "iss": float(n.iss or 0),
            "liquido": float(n.liquido or 0),
            "recebido": bool(n.recebido),
            "dataRecebimento": n.data_recebimento.strftime("%Y-%m-%d") if n.data_recebimento else "",
        })

    month_data = defaultdict(lambda: {"notas": 0, "bruto": 0.0, "inss": 0.0, "ir": 0.0, "iss": 0.0, "liquido": 0.0})
    for n in notes_list:
        k = n["mes"]
        month_data[k]["notas"] += 1
        for f in ("bruto", "inss", "ir", "iss", "liquido"):
            month_data[k][f] += n[f]

    summary = []
    for mes in _MESES_ORDER:
        if mes in month_data:
            d = month_data[mes]
            summary.append({
                "notas": d["notas"],
                "bruto": round(d["bruto"], 2),
                "inss": round(d["inss"], 2),
                "ir": round(d["ir"], 2),
                "iss": round(d["iss"], 2),
                "liquido": round(d["liquido"], 2),
                "mes": mes,
            })

    return (
        json.dumps(notes_list, ensure_ascii=False, separators=(",", ":")),
        json.dumps(summary,    ensure_ascii=False, separators=(",", ":")),
    )


@faturamento_bp.route("/")
def index():
    from core.timestamps import ler_timestamps
    ts = ler_timestamps()
    return render_template("faturamento/index.html", ultima_atualizacao=ts.get("faturamento", "—"))


@faturamento_bp.route("/dashboard")
@login_required
def dashboard():
    notes_js, summary_js = _build_dashboard_data(current_user.org_id)
    return render_template("faturamento/dashboard.html", notes_js=notes_js, summary_js=summary_js)


@faturamento_bp.route("/notas/<int:nr>/recebido", methods=["POST"])
@login_required
def nota_recebido(nr):
    from app.models import FaturamentoNota
    nota = FaturamentoNota.query.filter_by(
        org_id=current_user.org_id, nr=nr, excluido=False
    ).first_or_404()

    data = request.get_json(silent=True) or {}
    nota.recebido = bool(data.get("recebido", False))

    data_str = (data.get("data_recebimento") or "").strip()
    if data_str:
        try:
            nota.data_recebimento = _date.fromisoformat(data_str)
        except ValueError:
            nota.data_recebimento = None
    else:
        nota.data_recebimento = None

    db.session.commit()
    return jsonify(ok=True, recebido=nota.recebido)


@login_required
@faturamento_bp.route("/atualizar", methods=["POST"])
def atualizar():
    xml_file = request.files.get("xml")
    xlsx_file = request.files.get("xlsx")
    if not xml_file or not xml_file.filename.endswith(".xml"):
        flash("Envie um arquivo .xml de NFS-e.", "error")
        return redirect(url_for("faturamento.index"))

    xml_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xml")
    xml_tmp.write(xml_file.read())
    xml_tmp.close()
    xml_path = Path(xml_tmp.name)

    r2_warn = ""
    xlsx_bytes = None

    if xlsx_file and xlsx_file.filename.endswith(".xlsx"):
        xlsx_bytes = xlsx_file.read()
        try:
            r2.upload(_R2_XLSX, xlsx_bytes, _XLSX_CONTENT_TYPE)
        except Exception:
            r2_warn = _R2_WARN
    else:
        # Sem upload: tenta R2, depois disco local
        try:
            xlsx_bytes = r2.download(_R2_XLSX)
        except Exception:
            xlsx_bytes = None
            r2_warn = _R2_WARN
        if not xlsx_bytes:
            local = _xlsx_path()
            if local.exists():
                xlsx_bytes = local.read_bytes()
        if not xlsx_bytes:
            flash("Envie também a planilha .xlsx de faturamento (primeira vez).", "error")
            xml_path.unlink(missing_ok=True)
            return redirect(url_for("faturamento.index"))

    try:
        from app.blueprints.faturamento.updater import (
            parse_xml, criar_aba_mes, atualizar_resumo, carregar_workbook,
        )

        notas = parse_xml(str(xml_path))
        if not notas:
            flash("Nenhuma nota encontrada no XML.", "error")
            return redirect(url_for("faturamento.index"))

        mes = notas[0]["emissao"].month
        ano = notas[0]["emissao"].year
        MESES_PT = {1:"JANEIRO",2:"FEVEREIRO",3:"MARÇO",4:"ABRIL",5:"MAIO",6:"JUNHO",
                    7:"JULHO",8:"AGOSTO",9:"SETEMBRO",10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"}
        nome_aba = f"{MESES_PT[mes]} {ano}"

        wb = carregar_workbook(xlsx_bytes)
        abas_mes = [s for s in wb.sheetnames if s != "RESUMO"]
        template_aba = abas_mes[-1]
        subtotal_row, col_map = criar_aba_mes(wb, notas, mes, ano, nome_aba, template_aba)
        atualizar_resumo(wb, mes, subtotal_row, col_map, nome_aba)

        out = io.BytesIO()
        wb.save(out)
        xlsx_atualizado = out.getvalue()

        # Persiste xlsx atualizado no R2
        try:
            r2.upload(_R2_XLSX, xlsx_atualizado, _XLSX_CONTENT_TYPE)
        except Exception:
            r2_warn = _R2_WARN

        # Persiste notas no banco PostgreSQL
        from app.models import FaturamentoNota
        org_id = current_user.org_id if current_user.is_authenticated else 1
        for n in notas:
            exists = FaturamentoNota.query.filter_by(org_id=org_id, nr=n["nr"]).first()
            if not exists:
                emissao = n["emissao"].date() if hasattr(n["emissao"], "date") else n["emissao"]
                db.session.add(FaturamentoNota(
                    org_id=org_id,
                    nr=n["nr"],
                    emissao=emissao,
                    contrato=n.get("contrato", ""),
                    orgao=n.get("orgao", ""),
                    municipio=n.get("municipio", ""),
                    tipo=n.get("tipo", ""),
                    bruto=n.get("bruto", 0),
                    inss=n.get("inss", 0),
                    ir=n.get("ir", 0),
                    iss=n.get("iss", 0),
                    liquido=n.get("liquido", 0),
                ))
        db.session.commit()

        from core.timestamps import salvar_timestamp
        salvar_timestamp("faturamento")

        flash(f"Planilha atualizada: {len(notas)} notas de {MESES_PT[mes]}/{ano} importadas.{r2_warn}", "ok")
    except Exception as e:
        flash(f"Erro ao processar: {e}", "error")
    finally:
        xml_path.unlink(missing_ok=True)

    return redirect(url_for("faturamento.index"))
