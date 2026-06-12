import io
import os
import tempfile
from pathlib import Path
from flask import render_template, request, send_from_directory, current_app, flash, redirect, url_for

from app.blueprints.faturamento import faturamento_bp


@faturamento_bp.route("/")
def index():
    return render_template("faturamento/index.html")


@faturamento_bp.route("/dashboard")
def dashboard():
    folder = Path(current_app.static_folder) / "ferramentas" / "faturamento"
    return send_from_directory(folder, "dashboard.html")


@faturamento_bp.route("/atualizar", methods=["POST"])
def atualizar():
    xml_file = request.files.get("xml")
    xlsx_file = request.files.get("xlsx")
    if not xml_file or not xml_file.filename.endswith(".xml"):
        flash("Envie um arquivo .xml de NFS-e.", "error")
        return redirect(url_for("faturamento.index"))

    # Salva XML em temp
    xml_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xml")
    xml_tmp.write(xml_file.read())
    xml_tmp.close()
    xml_path = Path(xml_tmp.name)

    # Resolve caminho do xlsx
    instance_dir = Path(current_app.instance_path) / "faturamento"
    instance_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = instance_dir / "Faturamento 2026.xlsx"

    if xlsx_file and xlsx_file.filename.endswith(".xlsx"):
        xlsx_path.write_bytes(xlsx_file.read())
    elif not xlsx_path.exists():
        flash("Envie também a planilha .xlsx de faturamento (primeira vez).", "error")
        xml_path.unlink(missing_ok=True)
        return redirect(url_for("faturamento.index"))

    try:
        from app.blueprints.faturamento.updater import parse_xml, criar_aba_mes, atualizar_resumo
        from openpyxl import load_workbook
        import re as _re

        notas = parse_xml(str(xml_path))
        if not notas:
            flash("Nenhuma nota encontrada no XML.", "error")
            return redirect(url_for("faturamento.index"))

        mes = notas[0]["emissao"].month
        ano = notas[0]["emissao"].year
        MESES_PT = {1:"JANEIRO",2:"FEVEREIRO",3:"MARÇO",4:"ABRIL",5:"MAIO",6:"JUNHO",
                    7:"JULHO",8:"AGOSTO",9:"SETEMBRO",10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"}
        nome_aba = f"{MESES_PT[mes]} {ano}"

        wb = load_workbook(str(xlsx_path))
        abas_mes = [s for s in wb.sheetnames if s != "RESUMO"]
        template_aba = abas_mes[-1]
        subtotal_row, col_map = criar_aba_mes(wb, notas, mes, ano, nome_aba, template_aba)
        atualizar_resumo(wb, mes, subtotal_row, col_map, nome_aba)
        wb.save(str(xlsx_path))

        flash(f"Planilha atualizada: {len(notas)} notas de {MESES_PT[mes]}/{ano} importadas.", "ok")
    except Exception as e:
        flash(f"Erro ao processar: {e}", "error")
    finally:
        xml_path.unlink(missing_ok=True)

    return redirect(url_for("faturamento.index"))
