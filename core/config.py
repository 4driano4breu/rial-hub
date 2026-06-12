# Constantes de negócio do Contrato 037/2021 – AGESUL/RIAL
# Altere aqui sem tocar na lógica de cálculo.

ALIQUOTAS: dict[str, float] = {
    "pav":      0.10,
    "canteiro": 0.35,
    "rocada":   0.35,
    "terra":    0.15,
    "inss":     0.11,
}

CIDADE_DISPLAY: dict[str, str] = {
    "BATAGUASSU":          "BATAGUASSU",
    "BRASILANDIA":         "BRASILANDIA",
    "RIBAS DO RIO PARDO":  "RIBAS DO RIO DO PARDO",
    "SANTA RITA DO PARDO": "SANTA RITA DO PARDO",
    "TRES LAGOAS":         "TRES LAGOAS",
}

SERVICE_LABELS: dict[str, str] = {
    "pav":      "Pavimentação",
    "canteiro": "Canteiro",
    "rocada":   "Roçada",
    "terra":    "Terraplenagem",
}

# Mapeamento de seção do PDF de reajuste → categoria interna
SECAO_PARA_CAT: dict[str, str] = {
    "01": "rocada",
    "02": "terra",
    "03": "adm",
    "04": "canteiro",
    "05": "pav",
}

CONTRATO_HEADER = (
    "MANUTENÇÃO E CONSERVAÇÃO DAS RODOVIAS PAVIMENTADAS E NÃO PAVIMENTADAS, "
    "DA MALHA RODOVIÁRIA DA 3ª RESIDÊNCIA REGIONAL DE TRÊS LAGOAS/MS – SETOR B, "
    "PROCESSO Nº 57/101.086/2020 – CONTRATO Nº 037/2021 – CADASTRO NACIONAL DE "
    "OBRAS Nº 90.006.16075/77, SERVIÇOS REALIZADOS NO MUNICÍPIO DE {cidade} - MS. "
)

REAJ_HEADER = (
    "REAJUSTAMENTO MANUTENÇÃO E CONSERVAÇÃO DAS RODOVIAS PAVIMENTADAS E NÃO "
    "PAVIMENTADAS, DA MALHA RODOVIÁRIA DA 3ª RESIDÊNCIA REGIONAL DE TRÊS "
    "LAGOAS/MS – SETOR B, PROCESSO Nº 57/003.871/2021 – CONTRATO Nº 037/2021 "
    "– CADASTRO NACIONAL DE OBRA – CNO Nº 90.006.16075/77, SERVIÇOS REALIZADOS "
    "NO MUNICÍPIO DE {cidade} - MS. "
)

INSS_ISENTO = "INSS ISENTO CONFORME ART.130 PARÁGRAFO 1 IN RFB 2110 DE 17/10/2022"
BASE_CALC   = "BASE DE CÁLCULO:"
ADM_LABEL   = "Administração"
MED_PARCIAL = "{num} MEDIÇÃO PARCIAL, PERÍODO: {periodo} – R$ {total}"
MED_REAJ    = "{num} MEDIÇÃO DE REAJUSTAMENTO, PERÍODO: {periodo}. – R$ {total}"
TOTAL_MED   = "TOTAL DAS MEDIÇÕES: R$ {total}"
