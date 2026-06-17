import os
from pathlib import Path

_BASE = Path(__file__).parent.parent
_DEFAULT_DB = "sqlite:///" + str(_BASE / "instance" / "obria.db")


def _db_url():
    url = os.environ.get("DATABASE_URL", _DEFAULT_DB)
    # Railway usa "postgres://", SQLAlchemy 2.x requer "postgresql://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")

    # Banco de dados
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sessão / cookies
    _prod = os.environ.get("FLASK_ENV") == "production"
    SESSION_COOKIE_SECURE   = _prod
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE  = _prod
    REMEMBER_COOKIE_HTTPONLY = True

    # CSRF
    WTF_CSRF_ENABLED = True

    # Uploads
    UPLOAD_FOLDER         = str(_BASE / "uploads")
    MAX_CONTENT_LENGTH    = 32 * 1024 * 1024  # 32 MB
    ALLOWED_EXTENSIONS    = {"xlsx", "pdf"}

    # Cloudflare R2 (Fase 0.3)
    R2_ACCOUNT_ID        = os.environ.get("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID     = os.environ.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME       = os.environ.get("R2_BUCKET_NAME", "obria-storage")
    R2_PUBLIC_URL        = os.environ.get("R2_PUBLIC_URL", "")
