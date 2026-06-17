"""
Wrapper para Cloudflare R2 (S3-compatible).
Degrada graciosamente se as variáveis R2_* não estiverem configuradas.
"""
import boto3
from botocore.exceptions import ClientError
from flask import current_app


def _ready() -> bool:
    return bool(
        current_app.config.get("R2_ACCOUNT_ID")
        and current_app.config.get("R2_ACCESS_KEY_ID")
        and current_app.config.get("R2_SECRET_ACCESS_KEY")
        and current_app.config.get("R2_BUCKET_NAME")
    )


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{current_app.config['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=current_app.config["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def upload(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    if not _ready():
        return
    _client().put_object(
        Bucket=current_app.config["R2_BUCKET_NAME"],
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def download(key: str) -> bytes | None:
    if not _ready():
        return None
    try:
        resp = _client().get_object(Bucket=current_app.config["R2_BUCKET_NAME"], Key=key)
        return resp["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def exists(key: str) -> bool:
    if not _ready():
        return False
    try:
        _client().head_object(Bucket=current_app.config["R2_BUCKET_NAME"], Key=key)
        return True
    except ClientError:
        return False
