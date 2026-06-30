import json
import tempfile
from collections import defaultdict
from datetime import date as _date
from pathlib import Path
from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import current_user, login_required

from app.blueprints.faturamento import faturamento_bp
from app.extensions import db

_MESES_PT = {1:"JANEIRO",2:"FEVEREIRO",3:"MARÇO",4:"ABRIL",5:"MAIO",6:"JUNHO",
             7:"JULHO",8:"AGOSTO",9:"SETEMBRO",10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"}
_MESES_ORDER = list(_MESES_PT.values())



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


@faturamento_bp.route("/importar-recebimentos", methods=["POST"])
@login_required
def importar_recebimentos():
    json_file = request.files.get("json")
    if not json_file or not json_file.filename.endswith(".json"):
        flash("Envie um arquivo .json de recebimentos.", "error")
        return redirect(url_for("faturamento.index"))

    try:
        from app.models import FaturamentoNota
        dados = json.loads(json_file.read().decode("utf-8"))
        org_id = current_user.org_id
        atualizadas = nao_encontradas = 0

        for nr_str, info in dados.items():
            nr = int(nr_str)
            nota = FaturamentoNota.query.filter_by(org_id=org_id, nr=nr, excluido=False).first()
            if nota is None:
                nao_encontradas += 1
                continue
            nota.recebido = bool(info.get("recebido", False))
            data_str = (info.get("dataRecebimento") or "").strip()
            try:
                nota.data_recebimento = _date.fromisoformat(data_str) if data_str else None
            except ValueError:
                nota.data_recebimento = None
            atualizadas += 1

        db.session.commit()
        msg = f"{atualizadas} nota(s) de recebimento importadas."
        if nao_encontradas:
            msg += f" {nao_encontradas} não encontradas no banco (importe o XML primeiro)."
        flash(msg, "ok")
    except Exception as e:
        flash(f"Erro ao importar recebimentos: {e}", "error")

    return redirect(url_for("faturamento.index"))


@login_required
@faturamento_bp.route("/atualizar", methods=["POST"])
def atualizar():
    xml_file = request.files.get("xml")
    if not xml_file or not xml_file.filename.endswith(".xml"):
        flash("Envie um arquivo .xml de NFS-e.", "error")
        return redirect(url_for("faturamento.index"))

    xml_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xml")
    xml_tmp.write(xml_file.read())
    xml_tmp.close()
    xml_path = Path(xml_tmp.name)

    try:
        from app.blueprints.faturamento.updater import parse_xml
        from app.models import FaturamentoNota

        notas = parse_xml(str(xml_path))
        if not notas:
            flash("Nenhuma nota encontrada no XML.", "error")
            return redirect(url_for("faturamento.index"))

        org_id = current_user.org_id
        mes = notas[0]["emissao"].month
        ano = notas[0]["emissao"].year

        novas = atualizadas = 0
        for n in notas:
            emissao = n["emissao"].date() if hasattr(n["emissao"], "date") else n["emissao"]
            existing = FaturamentoNota.query.filter_by(org_id=org_id, nr=n["nr"]).first()
            if existing:
                existing.emissao  = emissao
                existing.bruto    = n.get("valor_bruto", 0)
                existing.inss     = n.get("inss", 0)
                existing.ir       = n.get("ir", 0)
                existing.iss      = n.get("iss", 0)
                existing.liquido  = n.get("liquido", 0)
                existing.orgao    = n.get("orgao") or existing.orgao
                if n.get("contrato"):
                    existing.contrato = n["contrato"]
                if n.get("municipio"):
                    existing.municipio = n["municipio"]
                atualizadas += 1
            else:
                db.session.add(FaturamentoNota(
                    org_id=org_id,
                    nr=n["nr"],
                    emissao=emissao,
                    contrato=n.get("contrato", ""),
                    orgao=n.get("orgao", ""),
                    municipio=n.get("municipio", ""),
                    tipo=n.get("tipo", ""),
                    bruto=n.get("valor_bruto", 0),
                    inss=n.get("inss", 0),
                    ir=n.get("ir", 0),
                    iss=n.get("iss", 0),
                    liquido=n.get("liquido", 0),
                ))
                novas += 1
        db.session.commit()

        from core.timestamps import salvar_timestamp
        salvar_timestamp("faturamento")

        msg = f"{novas} nota(s) importadas"
        if atualizadas:
            msg += f", {atualizadas} atualizada(s)"
        msg += f" de {_MESES_PT[mes]}/{ano}."
        flash(msg, "ok")
    except Exception as e:
        flash(f"Erro ao processar XML: {e}", "error")
    finally:
        xml_path.unlink(missing_ok=True)

    return redirect(url_for("faturamento.index"))
