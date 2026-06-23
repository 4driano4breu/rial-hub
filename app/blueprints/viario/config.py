import os, shutil
TESSERACT_CMD = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ── Serviços disponíveis ─────────────────────────────────────────
SERVICOS_GPS = [
    "Cascalho", "Aterro", "Conformação", "Raspagem", "Caiação", "Limpeza", "Roçada"
]

SERVICOS_KM_FOTO = [
    "Roçada", "Caiação", "Limpeza",
]

ROTAS_KM_FOTO = [
    "MS 395 - Entre Bataguassu/Brasilândia",
    "MS 040 - Entre Campo Grande/Santa Rita",
    "MS 338 - Entre Santa Rita/Bataguassu",
]

# ── Rodovias (sistema cascalho / GPS) ────────────────────────────
RODOVIAS = {
    "MS 245": {
        "inicio": (-19.994401884147283, -54.39235067983997),
        "inicio_corrigido": (-19.9969789894005, -54.04276728629854),
        "limite_km": 99,
        "ajuste_km": 40,
        "descricao": "MS 245",
        "modo_calculo": "limite_com_correcao",
    },
    "MS 441": {
        "inicio": (-19.909598, -54.371246),
        "inicio_corrigido": (-19.817516, -54.193835),
        "limite_km": 44,
        "ajuste_km": 20,
        "descricao": "MS 441",
        "modo_calculo": "limite_com_correcao",
    },
    "MS 438": {
        "inicio": (-19.48246639012942, -53.810120937526634),
        "descricao": "MS 438",
        "modo_calculo": "simples",
    },
    "MS 338": {
        "inicio": (-21.22952855040712, -52.95346154721126),
        "descricao": "MS 338",
        "modo_calculo": "simples",
    },
    "MS 134": {
        "inicio": (-21.229582, -52.953494),
        "descricao": "MS 134",
        "modo_calculo": "simples",
    },
    "MS 357": {
        "inicio": (-20.360606328566536, -53.6998187046927),
        "descricao": "MS 357",
        "modo_calculo": "simples",
    },
    "MS 456": {
        "inicio": (-20.592464486652297, -53.25128852883528),
        "descricao": "MS 456",
        "modo_calculo": "simples",
    },
    "MS 459": {
        "inicio": (-21.040902755947414, -52.48711664352654),
        "descricao": "MS 459",
        "modo_calculo": "simples",
    },
    "MS 040": {
        "inicio": (-21.251334549908613, -52.05551707116459),
        "descricao": "MS 040",
        "modo_calculo": "simples",
    },
    "MS 331": {
        "inicio": (-19.877483, -54.491623),
        "descricao": "MS 331",
        "modo_calculo": "simples",
    },
}

# ── Tapa-Buraco (dois pontos de origem) ──────────────────────────
TAPA_BURACO = {
    "ponto_cg":     (-20.555483, -54.555274),   # Campo Grande
    "ponto_sr":     (-21.306168, -52.823840),   # Santa Rita
    "limite_cg":    224,                         # km — acima disso usa SR
    "ajuste_sr":    285,                         # offset fixo adicionado à dist. SR
    "descricao_cg": "Tapa Buraco - MS 040 - Entre Campo Grande/Santa Rita",
    "descricao_sr": "Tapa Buraco - MS 338 - Santa Rita",
}
