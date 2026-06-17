from datetime import date
from flask import send_from_directory, current_app, render_template, jsonify, request
from flask_login import current_user
from pathlib import Path
from app.blueprints.ferramentas import ferramentas_bp
from app.extensions import db, csrf


@ferramentas_bp.route("/")
def index():
    return render_template("ferramentas/index.html")


def _ferramenta(subdir: str, filename: str):
    folder = Path(current_app.static_folder) / "ferramentas" / subdir
    return send_from_directory(folder, filename)


@ferramentas_bp.route("/medicao")
def medicao():
    return _ferramenta("faz_tudo", "medicao_pavimentacao_v6.0.html")


@ferramentas_bp.route("/le-doc")
def le_doc():
    return _ferramenta("le_doc", "preenchimento.html")


@ferramentas_bp.route("/abastecimento")
def abastecimento():
    return _ferramenta("abastecimento", "Dashboard_Abastecimento.html")


@ferramentas_bp.route("/notas-html")
def notas_html():
    return _ferramenta("notas", "notas_037.html")


@csrf.exempt
@ferramentas_bp.route("/api/producao", methods=["POST"])
def api_producao():
    from app.models import OperacaoProducao, RegistroProducao

    payload = request.get_json(force=True, silent=True) or {}
    action = payload.get("action")
    org_id = current_user.org_id if current_user.is_authenticated else 1

    if action == "ultimoTicket":
        last = (
            OperacaoProducao.query.filter_by(org_id=org_id)
            .order_by(OperacaoProducao.ticket_fim.desc())
            .first()
        )
        proximo = (last.ticket_fim + 1) if (last and last.ticket_fim) else 1001
        return jsonify(ok=True, proximoTicket=proximo)

    if action == "salvar":
        data = payload.get("payload", {})
        modo = data.get("modo", "tb")
        data_str = data.get("data", "")
        ticket_ini = int(data.get("ticketInicio", 1001))
        ticket_fim = int(data.get("ticketFim", ticket_ini))
        total = int(data.get("totalCaminhoes", 0))
        registros = data.get("registros", [])

        try:
            d, m, y = data_str.split("/")
            data_op = date(int(y), int(m), int(d))
        except (ValueError, AttributeError):
            data_op = date.today()

        op = OperacaoProducao(
            org_id=org_id,
            modo=modo,
            data_operacao=data_op,
            ticket_inicio=ticket_ini,
            ticket_fim=ticket_fim,
            total_caminhoes=total,
            criado_por=current_user.id if current_user.is_authenticated else None,
        )
        db.session.add(op)
        db.session.flush()

        for r in registros:
            tara = float(str(r.get("tara", "0")).replace(",", ".") or 0)
            peso = float(str(r.get("peso", "0")).replace(",", ".") or 0)
            db.session.add(RegistroProducao(
                operacao_id=op.id,
                org_id=org_id,
                placa=r.get("placa", ""),
                motorista=r.get("motorista", ""),
                entrada=r.get("entrada", ""),
                saida=r.get("saida", ""),
                tara=tara,
                peso=peso,
                regiao=r.get("regiao", ""),
            ))

        db.session.commit()
        return jsonify(ok=True, id=op.id)

    if action == "buscar":
        filtros = payload.get("filtros", {})
        q = OperacaoProducao.query.filter_by(org_id=org_id)

        if filtros.get("modo"):
            q = q.filter(OperacaoProducao.modo == filtros["modo"])

        for field, attr in (("dataIni", ">="), ("dataFim", "<=")):
            val = filtros.get(field, "")
            if val:
                try:
                    d, m, y = val.split("/")
                    dt = date(int(y), int(m), int(d))
                    if attr == ">=":
                        q = q.filter(OperacaoProducao.data_operacao >= dt)
                    else:
                        q = q.filter(OperacaoProducao.data_operacao <= dt)
                except (ValueError, AttributeError):
                    pass

        ops = q.order_by(
            OperacaoProducao.data_operacao.desc(),
            OperacaoProducao.id.desc()
        ).limit(100).all()

        regiao_filtro = (filtros.get("regiao") or "").upper()
        grupos = []
        for op in ops:
            regioes = set()
            regs = []
            ti = op.ticket_inicio or 0
            for i, r in enumerate(op.registros):
                regs.append({
                    "ticket": ti + i,
                    "placa": r.placa or "",
                    "motorista": r.motorista or "",
                    "entrada": r.entrada or "",
                    "saida": r.saida or "",
                    "tara": str(r.tara or ""),
                    "peso": str(r.peso or ""),
                    "regiao": r.regiao or "",
                })
                if r.regiao:
                    regioes.add(r.regiao)

            if regiao_filtro and regiao_filtro not in {rg.upper() for rg in regioes}:
                continue

            grupos.append({
                "id": op.id,
                "data": op.data_operacao.strftime("%d/%m/%Y") if op.data_operacao else "",
                "modo": op.modo or "tb",
                "regioes": list(regioes),
                "ticketInicio": op.ticket_inicio or 0,
                "ticketFim": op.ticket_fim or 0,
                "totalCaminhoes": op.total_caminhoes or 0,
                "registros": regs,
                "dataSalvamento": op.criado_em.strftime("%d/%m/%Y %H:%M") if op.criado_em else "",
            })

        return jsonify(ok=True, grupos=grupos)

    if action == "excluir":
        op_id = payload.get("id")
        op = OperacaoProducao.query.filter_by(id=op_id, org_id=org_id).first()
        if not op:
            return jsonify(ok=False, erro="Não encontrado")
        db.session.delete(op)
        db.session.commit()
        return jsonify(ok=True)

    return jsonify(ok=False, erro="Ação desconhecida")
