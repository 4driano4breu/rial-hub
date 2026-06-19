from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.blueprints.dados import dados_bp
from app.extensions import db
from app.models import (
    UsinagemRegistro, FaturamentoNota, ChecklistExecucao, AuditLog,
)

PER_PAGE = 50


def _require_admin(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.has_role("ADMIN", "SUPERADMIN"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _log_audit(org_id, usuario_id, acao, modulo, registro_id, campos=None):
    log = AuditLog(
        org_id=org_id, usuario_id=usuario_id, acao=acao,
        modulo=modulo, registro_id=registro_id, campos=campos or {},
    )
    db.session.add(log)


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_decimal(value):
    value = (value or "").strip().replace(",", ".")
    if value == "":
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _page():
    try:
        p = int(request.args.get("p", 1))
    except (TypeError, ValueError):
        p = 1
    return max(p, 1)


def _diff(registro, campo, novo):
    """Retorna {'de': antigo, 'para': novo} se mudou, senão None. Aplica o valor."""
    antigo = getattr(registro, campo)
    if isinstance(antigo, Decimal) and isinstance(novo, Decimal):
        mudou = antigo != novo
    else:
        mudou = antigo != novo
    if not mudou:
        return None
    setattr(registro, campo, novo)

    def _ser(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        if isinstance(v, Decimal):
            return str(v)
        return v

    return {"de": _ser(antigo), "para": _ser(novo)}


# ── Visão geral ────────────────────────────────────────────────────────────────

@dados_bp.route("/")
@_require_admin
def index():
    org_id = current_user.org_id
    stats = {
        "usinagem": UsinagemRegistro.query.filter_by(org_id=org_id, excluido=False).count(),
        "usinagem_lixeira": UsinagemRegistro.query.filter_by(org_id=org_id, excluido=True).count(),
        "faturamento": FaturamentoNota.query.filter_by(org_id=org_id, excluido=False).count(),
        "faturamento_lixeira": FaturamentoNota.query.filter_by(org_id=org_id, excluido=True).count(),
        "checklist": ChecklistExecucao.query.filter_by(org_id=org_id).count(),
        "auditoria": AuditLog.query.filter_by(org_id=org_id).count(),
    }
    return render_template("dados/index.html", stats=stats)


# ── Usinagem ───────────────────────────────────────────────────────────────────

@dados_bp.route("/usinagem/")
@_require_admin
def usinagem_lista():
    org_id = current_user.org_id
    q = request.args.get("q", "").strip()
    de = _parse_date(request.args.get("de"))
    ate = _parse_date(request.args.get("ate"))
    regiao = request.args.get("regiao", "").strip()
    lixeira = request.args.get("lixeira") == "1"

    query = UsinagemRegistro.query.filter_by(org_id=org_id, excluido=lixeira)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            UsinagemRegistro.ticket.ilike(like),
            UsinagemRegistro.placa.ilike(like),
            UsinagemRegistro.motorista.ilike(like),
        ))
    if de:
        query = query.filter(UsinagemRegistro.data_operacao >= de)
    if ate:
        query = query.filter(UsinagemRegistro.data_operacao <= ate)
    if regiao:
        query = query.filter(UsinagemRegistro.regiao == regiao)

    pg = query.order_by(UsinagemRegistro.data_operacao.desc().nullslast(),
                        UsinagemRegistro.id.desc()).paginate(
        page=_page(), per_page=PER_PAGE, error_out=False)

    regioes = [r[0] for r in db.session.query(UsinagemRegistro.regiao)
               .filter_by(org_id=org_id).distinct().all() if r[0]]

    return render_template("dados/usinagem_lista.html",
                           pg=pg, lixeira=lixeira, regioes=regioes,
                           filtros={"q": q, "de": request.args.get("de", ""),
                                    "ate": request.args.get("ate", ""), "regiao": regiao})


@dados_bp.route("/usinagem/<int:id>/editar", methods=["GET", "POST"])
@_require_admin
def usinagem_editar(id):
    org_id = current_user.org_id
    reg = UsinagemRegistro.query.filter_by(id=id, org_id=org_id).first_or_404()

    if request.method == "POST":
        campos = {}
        for nome, valor in [
            ("data_operacao", _parse_date(request.form.get("data_operacao"))),
            ("placa", request.form.get("placa", "").strip()),
            ("motorista", request.form.get("motorista", "").strip()),
            ("peso_bruto", _parse_decimal(request.form.get("peso_bruto"))),
            ("tara", _parse_decimal(request.form.get("tara"))),
            ("peso_liquido", _parse_decimal(request.form.get("peso_liquido"))),
            ("regiao", request.form.get("regiao", "").strip()),
            ("contrato", request.form.get("contrato", "").strip()),
        ]:
            d = _diff(reg, nome, valor)
            if d:
                campos[nome] = d

        try:
            if campos:
                _log_audit(org_id, current_user.id, "EDIT", "usinagem", reg.id, campos)
            db.session.commit()
            flash("Registro de usinagem atualizado." if campos else "Nenhuma alteração feita.", "ok")
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar alterações.", "error")
        return redirect(url_for("dados.usinagem_lista"))

    return render_template("dados/usinagem_editar.html", reg=reg)


@dados_bp.route("/usinagem/<int:id>/excluir", methods=["POST"])
@_require_admin
def usinagem_excluir(id):
    org_id = current_user.org_id
    reg = UsinagemRegistro.query.filter_by(id=id, org_id=org_id, excluido=False).first_or_404()
    try:
        reg.excluido = True
        reg.excluido_em = datetime.utcnow()
        reg.excluido_por = current_user.id
        _log_audit(org_id, current_user.id, "DELETE", "usinagem", reg.id)
        db.session.commit()
        flash(f"Registro {reg.ticket or reg.id} movido para a lixeira.", "ok")
    except Exception:
        db.session.rollback()
        flash("Erro ao excluir registro.", "error")
    return redirect(url_for("dados.usinagem_lista"))


@dados_bp.route("/usinagem/<int:id>/restaurar", methods=["POST"])
@_require_admin
def usinagem_restaurar(id):
    org_id = current_user.org_id
    reg = UsinagemRegistro.query.filter_by(id=id, org_id=org_id, excluido=True).first_or_404()
    try:
        reg.excluido = False
        reg.excluido_em = None
        reg.excluido_por = None
        _log_audit(org_id, current_user.id, "RESTORE", "usinagem", reg.id)
        db.session.commit()
        flash(f"Registro {reg.ticket or reg.id} restaurado.", "ok")
    except Exception:
        db.session.rollback()
        flash("Erro ao restaurar registro.", "error")
    return redirect(url_for("dados.usinagem_lista", lixeira=1))


# ── Faturamento ────────────────────────────────────────────────────────────────

@dados_bp.route("/faturamento/")
@_require_admin
def faturamento_lista():
    org_id = current_user.org_id
    q = request.args.get("q", "").strip()
    de = _parse_date(request.args.get("de"))
    ate = _parse_date(request.args.get("ate"))
    recebido_raw = request.args.get("recebido", "")
    lixeira = request.args.get("lixeira") == "1"

    query = FaturamentoNota.query.filter_by(org_id=org_id, excluido=lixeira)
    if q:
        like = f"%{q}%"
        conds = [
            FaturamentoNota.contrato.ilike(like),
            FaturamentoNota.municipio.ilike(like),
        ]
        if q.isdigit():
            conds.append(FaturamentoNota.nr == int(q))
        query = query.filter(or_(*conds))
    if de:
        query = query.filter(FaturamentoNota.emissao >= de)
    if ate:
        query = query.filter(FaturamentoNota.emissao <= ate)
    if recebido_raw in ("0", "1"):
        query = query.filter(FaturamentoNota.recebido == (recebido_raw == "1"))

    pg = query.order_by(FaturamentoNota.emissao.desc().nullslast(),
                        FaturamentoNota.id.desc()).paginate(
        page=_page(), per_page=PER_PAGE, error_out=False)

    return render_template("dados/faturamento_lista.html",
                           pg=pg, lixeira=lixeira,
                           filtros={"q": q, "de": request.args.get("de", ""),
                                    "ate": request.args.get("ate", ""),
                                    "recebido": recebido_raw})


@dados_bp.route("/faturamento/<int:id>/editar", methods=["GET", "POST"])
@_require_admin
def faturamento_editar(id):
    org_id = current_user.org_id
    nota = FaturamentoNota.query.filter_by(id=id, org_id=org_id).first_or_404()

    if request.method == "POST":
        nr_raw = request.form.get("nr", "").strip()
        try:
            nr = int(nr_raw) if nr_raw else nota.nr
        except ValueError:
            flash("Número da nota inválido.", "error")
            return redirect(url_for("dados.faturamento_editar", id=id))

        campos = {}
        for nome, valor in [
            ("nr", nr),
            ("emissao", _parse_date(request.form.get("emissao")) or nota.emissao),
            ("contrato", request.form.get("contrato", "").strip()),
            ("orgao", request.form.get("orgao", "").strip()),
            ("municipio", request.form.get("municipio", "").strip()),
            ("tipo", request.form.get("tipo", "").strip()),
            ("bruto", _parse_decimal(request.form.get("bruto")) or Decimal(0)),
            ("inss", _parse_decimal(request.form.get("inss")) or Decimal(0)),
            ("ir", _parse_decimal(request.form.get("ir")) or Decimal(0)),
            ("iss", _parse_decimal(request.form.get("iss")) or Decimal(0)),
            ("liquido", _parse_decimal(request.form.get("liquido")) or Decimal(0)),
            ("recebido", request.form.get("recebido") == "1"),
            ("data_recebimento", _parse_date(request.form.get("data_recebimento"))),
        ]:
            d = _diff(nota, nome, valor)
            if d:
                campos[nome] = d

        try:
            if campos:
                _log_audit(org_id, current_user.id, "EDIT", "faturamento", nota.id, campos)
            db.session.commit()
            flash("Nota de faturamento atualizada." if campos else "Nenhuma alteração feita.", "ok")
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar. Verifique se o número da nota não está duplicado.", "error")
            return redirect(url_for("dados.faturamento_editar", id=id))
        return redirect(url_for("dados.faturamento_lista"))

    return render_template("dados/faturamento_editar.html", nota=nota)


@dados_bp.route("/faturamento/<int:id>/excluir", methods=["POST"])
@_require_admin
def faturamento_excluir(id):
    org_id = current_user.org_id
    nota = FaturamentoNota.query.filter_by(id=id, org_id=org_id, excluido=False).first_or_404()
    try:
        nota.excluido = True
        nota.excluido_em = datetime.utcnow()
        nota.excluido_por = current_user.id
        _log_audit(org_id, current_user.id, "DELETE", "faturamento", nota.id)
        db.session.commit()
        flash(f"Nota {nota.nr} movida para a lixeira.", "ok")
    except Exception:
        db.session.rollback()
        flash("Erro ao excluir nota.", "error")
    return redirect(url_for("dados.faturamento_lista"))


@dados_bp.route("/faturamento/<int:id>/restaurar", methods=["POST"])
@_require_admin
def faturamento_restaurar(id):
    org_id = current_user.org_id
    nota = FaturamentoNota.query.filter_by(id=id, org_id=org_id, excluido=True).first_or_404()
    try:
        nota.excluido = False
        nota.excluido_em = None
        nota.excluido_por = None
        _log_audit(org_id, current_user.id, "RESTORE", "faturamento", nota.id)
        db.session.commit()
        flash(f"Nota {nota.nr} restaurada.", "ok")
    except Exception:
        db.session.rollback()
        flash("Erro ao restaurar nota.", "error")
    return redirect(url_for("dados.faturamento_lista", lixeira=1))


# ── Auditoria ──────────────────────────────────────────────────────────────────

@dados_bp.route("/auditoria/")
@_require_admin
def auditoria():
    org_id = current_user.org_id
    modulo = request.args.get("modulo", "").strip()
    acao = request.args.get("acao", "").strip()
    usuario = request.args.get("usuario", "").strip()

    query = AuditLog.query.filter_by(org_id=org_id)
    if modulo:
        query = query.filter(AuditLog.modulo == modulo)
    if acao:
        query = query.filter(AuditLog.acao == acao)
    if usuario and usuario.isdigit():
        query = query.filter(AuditLog.usuario_id == int(usuario))

    pg = query.order_by(AuditLog.criado_em.desc()).paginate(
        page=_page(), per_page=PER_PAGE, error_out=False)

    from app.models import User
    usuarios = User.query.filter_by(org_id=org_id).order_by(User.nome).all()
    nomes = {u.id: u.nome for u in usuarios}

    return render_template("dados/auditoria.html",
                           pg=pg, usuarios=usuarios, nomes=nomes,
                           filtros={"modulo": modulo, "acao": acao, "usuario": usuario})
