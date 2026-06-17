"""
Helper para ler configurações por tenant.
Busca do organization.settings com fallback para os defaults do contrato RIAL 037/2021.
"""
from flask_login import current_user


_DEFAULTS = {
    "aliquotas": {
        "pav":      0.10,
        "canteiro": 0.35,
        "rocada":   0.35,
        "terra":    0.15,
        "inss":     0.11,
    },
    "usinagem": {
        "cap_aegea":       30.0,
        "cap_guariroba":   63.93,
        "composicao_cap":  0.051,
    },
    "contratos": [
        {"nome": "037/2021", "orgao": "AGESUL"}
    ],
}


def get_settings(org=None) -> dict:
    """Retorna settings da org com fallback para os defaults."""
    from app.models import Organization
    if org is None and current_user.is_authenticated:
        org = Organization.query.get(current_user.org_id)
    stored = (org.settings or {}) if org else {}
    merged = {}
    for key, default in _DEFAULTS.items():
        if isinstance(default, dict):
            merged[key] = {**default, **(stored.get(key) or {})}
        else:
            merged[key] = stored.get(key, default)
    return merged


def get_aliquotas(org=None) -> dict:
    return get_settings(org)["aliquotas"]


def get_usinagem_cfg(org=None) -> dict:
    return get_settings(org)["usinagem"]
