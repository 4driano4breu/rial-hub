import re
from pathlib import Path
from flask import render_template, request, send_file, flash, redirect, url_for
import io

from app.blueprints.notas import notas_bp
from app.blueprints.notas.logic import calcular_reajuste
from core.extractor import extrair_dados_xlsx, extrair_pdf_reajuste, fmt
from core.generator import gerar_word_medicao, gerar_word_reajuste


def _allowed(filename: str, exts: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


@notas_bp.route("/")
def index():
    return render_template("notas/index.html")


@notas_bp.route("/gerar-medicao", methods=["POST"])
def gerar_medicao():
    xlsx = request.files.get("xlsx")
    if not xlsx or not _allowed(xlsx.filename, {"xlsx"}):
        flash("Envie um arquivo .xlsx de medição.", "error")
        return redirect(url_for("notas.index"))

    try:
        info, cidades = extrair_dados_xlsx(xlsx)
        docx_bytes = gerar_word_medicao(info, cidades)
        digitos = re.sub(r"[^\d]", "", info["num_medicao"])
        filename = f"notas_{digitos}_medicao.docx"
        return send_file(
            io.BytesIO(docx_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        flash(f"Erro ao processar: {e}", "error")
        return redirect(url_for("notas.index"))


@notas_bp.route("/gerar-reajuste", methods=["POST"])
def gerar_reajuste():
    xlsx = request.files.get("xlsx")
    pdf  = request.files.get("pdf")
    if not xlsx or not _allowed(xlsx.filename, {"xlsx"}):
        flash("Envie o arquivo .xlsx de medição.", "error")
        return redirect(url_for("notas.index"))
    if not pdf or not _allowed(pdf.filename, {"pdf"}):
        flash("Envie o arquivo .pdf de reajuste.", "error")
        return redirect(url_for("notas.index"))

    try:
        info, cidades = extrair_dados_xlsx(xlsx)
        coefs, total_pdf, reaj_secao = extrair_pdf_reajuste(pdf)
        reajuste = calcular_reajuste(cidades, coefs, total_pdf, reaj_secao)
        docx_bytes = gerar_word_reajuste(info, reajuste)
        digitos = re.sub(r"[^\d]", "", info["num_medicao"])
        filename = f"reajuste_{digitos}_medicao.docx"
        return send_file(
            io.BytesIO(docx_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        flash(f"Erro ao processar: {e}", "error")
        return redirect(url_for("notas.index"))
