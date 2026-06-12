# -*- coding: utf-8 -*-
"""Lógica específica de reajustamento — distribuição proporcional por cidade."""
from core.config import ALIQUOTAS, SECAO_PARA_CAT
from core.extractor import fmt


def calcular_reajuste(
    cidades: dict,
    coefs_cat: dict,
    total_pdf: float,
    reaj_por_secao: dict,
) -> dict:
    """
    Distribui o reajuste por cidade proporcionalmente ao valor medido.
    Usa valores do PDF quando disponíveis; cai para coeficientes FGV caso contrário.
    A última cidade de cada categoria recebe o saldo para garantir soma exata.
    """
    reaj_cat: dict[str, float] = {}
    for secao, cat in SECAO_PARA_CAT.items():
        v = reaj_por_secao.get(secao, 0.0)
        reaj_cat[cat] = reaj_cat.get(cat, 0.0) + v

    usou_pdf = bool(reaj_cat and any(v > 0 for v in reaj_cat.values()))

    resultado: dict[str, dict[str, float]] = {
        nome: {k: 0.0 for k in ("adm", "pav", "canteiro", "rocada", "terra")}
        for nome in cidades
    }

    for cat in ("adm", "pav", "canteiro", "rocada", "terra"):
        if usou_pdf and reaj_cat.get(cat, 0) > 0:
            total_cat = reaj_cat[cat]
        else:
            total_med_cat = sum(v[cat] for v in cidades.values())
            total_cat = round(total_med_cat * coefs_cat.get(cat, 0), 2)

        total_med_cat = sum(v[cat] for v in cidades.values())
        if total_med_cat <= 0:
            continue

        cidades_cat = [(n, v[cat]) for n, v in cidades.items() if v[cat] > 0]
        acumulado = 0.0
        for i, (nome, med) in enumerate(cidades_cat):
            if i == len(cidades_cat) - 1:
                reaj_cidade = round(total_cat - acumulado, 2)
            else:
                reaj_cidade = round(total_cat * (med / total_med_cat), 2)
            resultado[nome][cat] = reaj_cidade
            acumulado += reaj_cidade

    for r in resultado.values():
        r["total"] = round(sum(r[k] for k in ("adm", "pav", "canteiro", "rocada", "terra")), 2)

    resultado = {n: r for n, r in resultado.items() if r["total"] > 0}

    # Ajuste residual: garante que a soma bate exatamente com o total do PDF
    calc_total = sum(r["total"] for r in resultado.values())
    diff = round(calc_total - (total_pdf or calc_total), 2)
    if diff != 0:
        ultimo = list(resultado.keys())[-1]
        for cat in ("terra", "rocada", "pav", "canteiro", "adm"):
            if resultado[ultimo][cat] > 0:
                resultado[ultimo][cat] = round(resultado[ultimo][cat] - diff, 2)
                resultado[ultimo]["total"] = round(resultado[ultimo]["total"] - diff, 2)
                break

    return resultado
