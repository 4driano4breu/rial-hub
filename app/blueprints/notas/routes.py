import re
import io
import tempfile
from pathlib import Path
from flask import render_template, request, send_file, flash, redirect, url_for, session
from flask_login import current_user, login_required

from app.blueprints.notas import notas_bp
from app.blueprints.notas.logic import calcular_reajuste
from core.extractor import extrair_dados_xlsx, extrair_pdf_reajuste
from core.generator import gerar_word_medicao, gerar_word_reajuste, gerar_texto_medicao, gerar_texto_reajuste
from core.extractor import fmt
from core.config import SERVICE_LABELS, CIDADE_DISPLAY
from app.org_settings import get_aliquotas


def _registrar_medicao(tipo: str, info: dict) -> None:
    try:
        from app.extensions import db
        from app.models import MedicaoRecord
        org_id = current_user.org_id if current_user.is_authenticated else 1
        user_id = current_user.id if current_user.is_authenticated else None
        db.session.add(MedicaoRecord(
            org_id=org_id,
            gerado_por=user_id,
            tipo=tipo,
            contrato=info.get("contrato", ""),
            periodo=info.get("num_medicao", ""),
        ))
        db.session.commit()
    except Exception:
        pass


def _allowed(filename: str, exts: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


def _save_upload(file_storage, suffix: str) -> Path:
    """Salva FileStorage em arquivo temporário e retorna o Path."""
    buf = file_storage.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(buf)
    tmp.close()
    return Path(tmp.name)


@notas_bp.route("/")
def index():
    return redirect(url_for("ferramentas.notas_html"))


@login_required
@notas_bp.route("/gerar-medicao", methods=["POST"])
def gerar_medicao():
    xlsx_file = request.files.get("xlsx")
    if not xlsx_file or not _allowed(xlsx_file.filename, {"xlsx"}):
        flash("Envie um arquivo .xlsx de medição.", "error")
        return redirect(url_for("notas.index"))

    tmp_path = None
    try:
        tmp_path = _save_upload(xlsx_file, ".xlsx")
        info, cidades = extrair_dados_xlsx(tmp_path)
        docx_bytes = gerar_word_medicao(info, cidades)
        _registrar_medicao("parcial", info)
        digitos = re.sub(r"[^\d]", "", info["num_medicao"])
        filename = f"notas_{digitos}_medicao.docx"

        preview = _build_preview_medicao(info, cidades)
        docx_b64 = __import__("base64").b64encode(docx_bytes).decode()
        total_geral = fmt(sum(v["total"] for v in cidades.values()))

        return render_template(
            "notas/resultado.html",
            info=info,
            preview=preview,
            filename=filename,
            docx_b64=docx_b64,
            modo="medicao",
            total_geral=total_geral,
        )
    except Exception as e:
        flash(f"Erro ao processar: {e}", "error")
        return redirect(url_for("notas.index"))
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except PermissionError:
                pass


@login_required
@notas_bp.route("/gerar-reajuste", methods=["POST"])
def gerar_reajuste():
    xlsx_file = request.files.get("xlsx")
    pdf_file  = request.files.get("pdf")
    if not xlsx_file or not _allowed(xlsx_file.filename, {"xlsx"}):
        flash("Envie o arquivo .xlsx de medição.", "error")
        return redirect(url_for("notas.index"))
    if not pdf_file or not _allowed(pdf_file.filename, {"pdf"}):
        flash("Envie o arquivo .pdf de reajuste.", "error")
        return redirect(url_for("notas.index"))

    tmp_xlsx = tmp_pdf = None
    try:
        tmp_xlsx = _save_upload(xlsx_file, ".xlsx")
        tmp_pdf  = _save_upload(pdf_file, ".pdf")
        info, cidades = extrair_dados_xlsx(tmp_xlsx)
        coefs, total_pdf, reaj_secao = extrair_pdf_reajuste(tmp_pdf)
        reajuste = calcular_reajuste(cidades, coefs, total_pdf, reaj_secao)
        docx_bytes = gerar_word_reajuste(info, reajuste)
        _registrar_medicao("reajustamento", info)
        digitos = re.sub(r"[^\d]", "", info["num_medicao"])
        filename = f"reajuste_{digitos}_medicao.docx"

        preview = _build_preview_reajuste(info, reajuste)
        docx_b64 = __import__("base64").b64encode(docx_bytes).decode()
        total_geral = fmt(sum(v["total"] for v in reajuste.values()))

        return render_template(
            "notas/resultado.html",
            info=info,
            preview=preview,
            filename=filename,
            docx_b64=docx_b64,
            modo="reajuste",
            total_geral=total_geral,
        )
    except Exception as e:
        flash(f"Erro ao processar: {e}", "error")
        return redirect(url_for("notas.index"))
    finally:
        for p in (tmp_xlsx, tmp_pdf):
            if p and p.exists():
                try:
                    p.unlink()
                except PermissionError:
                    pass


@notas_bp.route("/download", methods=["POST"])
def download():
    import base64
    docx_b64 = request.form.get("docx_b64", "")
    filename  = request.form.get("filename", "nota.docx")
    try:
        docx_bytes = base64.b64decode(docx_b64)
        return send_file(
            io.BytesIO(docx_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        flash(f"Erro no download: {e}", "error")
        return redirect(url_for("notas.index"))


# ── Helpers de preview ────────────────────────────────────────────────────────

def _build_preview_medicao(info: dict, cidades: dict) -> list:
    CORES = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"]
    ALIQUOTAS = get_aliquotas()
    preview = []
    for idx, (nome_upper, vals) in enumerate(cidades.items()):
        cidade_display = CIDADE_DISPLAY.get(nome_upper.rstrip(), nome_upper)
        servicos = []
        base_inss = 0.0
        for key in ("pav", "canteiro", "rocada", "terra"):
            aliq = ALIQUOTAS.get(key, 0)
            if vals[key] > 0:
                base = vals[key] * aliq
                base_inss += base
                servicos.append({"label": SERVICE_LABELS[key], "valor": fmt(vals[key]),
                                  "aliq": int(aliq * 100), "base": fmt(base)})
        preview.append({
            "nome": cidade_display,
            "total": fmt(vals["total"]),
            "cor": CORES[idx % len(CORES)],
            "servicos": servicos,
            "adm": fmt(vals["adm"]) if vals["adm"] > 0 else None,
            "base_inss": fmt(base_inss),
            "inss_val": fmt(base_inss * ALIQUOTAS.get("inss", 0)),
            "texto": gerar_texto_medicao(info, nome_upper, vals),
        })
    return preview


def _build_preview_reajuste(info: dict, reajuste: dict) -> list:
    CORES = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"]
    ALIQUOTAS = get_aliquotas()
    preview = []
    for idx, (nome, reaj) in enumerate(reajuste.items()):
        cidade_display = CIDADE_DISPLAY.get(nome.rstrip(), nome)
        servicos = []
        base_inss = 0.0
        for key in ("pav", "canteiro", "rocada", "terra"):
            aliq = ALIQUOTAS.get(key, 0)
            if reaj[key] > 0:
                base = reaj[key] * aliq
                base_inss += base
                servicos.append({"label": SERVICE_LABELS[key], "valor": fmt(reaj[key]),
                                  "aliq": int(aliq * 100), "base": fmt(base)})
        preview.append({
            "nome": cidade_display,
            "total": fmt(reaj["total"]),
            "cor": CORES[idx % len(CORES)],
            "servicos": servicos,
            "adm": fmt(reaj["adm"]) if reaj["adm"] > 0 else None,
            "base_inss": fmt(base_inss),
            "inss_val": fmt(base_inss * ALIQUOTAS.get("inss", 0)),
            "texto": gerar_texto_reajuste(info, nome, reaj),
        })
    return preview
