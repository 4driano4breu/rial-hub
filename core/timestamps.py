import json
from datetime import datetime
from pathlib import Path
from flask import current_app


def _ts_path() -> Path:
    p = Path(current_app.instance_path) / "timestamps.json"
    return p


def salvar_timestamp(modulo: str) -> None:
    path = _ts_path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[modulo] = datetime.now().strftime("%d/%m/%Y %H:%M")
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def ler_timestamps() -> dict:
    path = _ts_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
