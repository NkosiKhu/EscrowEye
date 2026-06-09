from __future__ import annotations

import os
from pathlib import Path

from app.core.config import settings

PROJECT_DIR = Path(__file__).resolve().parents[2]


def _load_env(key: str, value: str) -> None:
    if key and key not in os.environ:
        os.environ[key] = value


def load_local_creds() -> None:
    creds_path = PROJECT_DIR / "creds"
    if not creds_path.exists() or not creds_path.is_file():
        return
    lines = creds_path.read_text().splitlines()
    multi_key: str | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            _load_env(k.strip(), v.strip().strip('"').strip("'"))
            continue
        if line in ("key", "secret", "jwt"):
            multi_key = line
            continue
        if multi_key:
            _load_env(f"PINATA_{multi_key.upper()}", line)
            multi_key = None


load_local_creds()

OPENROUTER_API_KEY = settings.OPENROUTER_API_KEY
OPENROUTER_MODEL = settings.OPENROUTER_MODEL
UPLOAD_DIR = settings.UPLOAD_DIR
DB_PATH = settings.DATABASE_PATH
CORS_ORIGINS = settings.CORS_ORIGINS


def validate_production_env() -> None:
    if os.getenv("ENVIRONMENT", "development") != "production":
        return
    secret_raw = os.getenv("ESCROWEYE_SECRET", "")
    required = {
        "ESCROWEYE_SECRET": secret_raw,
        "HEDERA_OPERATOR_ID": os.getenv("HEDERA_OPERATOR_ID"),
        "HEDERA_OPERATOR_PRIVATE_KEY": os.getenv("HEDERA_OPERATOR_PRIVATE_KEY"),
        "PINATA_JWT": os.getenv("PINATA_JWT"),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        msg = f"Missing required production environment variables: {', '.join(missing)}"
        raise RuntimeError(msg)
    if secret_raw == "escroweye-dev-secret":
        msg = "ESCROWEYE_SECRET is set to the dev default in production mode. Set a strong random secret."
        raise RuntimeError(msg)
