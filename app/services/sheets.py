"""
Integração com Google Sheets API via service account.
Requer variável de ambiente GOOGLE_CREDENTIALS_JSON com o JSON da service account.
"""
import json
import logging
import os

_log = logging.getLogger(__name__)


def _creds_available() -> bool:
    return bool(os.environ.get("GOOGLE_CREDENTIALS_JSON"))


def ler_planilha(spreadsheet_id: str, range_name: str) -> list[dict]:
    """
    Lê uma aba do Google Sheets e retorna lista de dicts (cabeçalho = chave).
    Retorna lista vazia se credenciais não configuradas ou em caso de erro.
    """
    if not _creds_available():
        return []

    try:
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials

        creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
        creds = Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        rows = result.get("values", [])
        if not rows:
            return []
        headers = rows[0]
        return [
            dict(zip(headers, row + [""] * (len(headers) - len(row))))
            for row in rows[1:]
        ]
    except Exception as exc:
        _log.error("Google Sheets error: %s", exc)
        return []
