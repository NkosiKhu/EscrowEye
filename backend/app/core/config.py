from __future__ import annotations

import os
from pathlib import Path


class Settings:
    _instance: Settings | None = None
    _BASE_DIR: Path
    _PROJECT_DIR: Path
    _UPLOAD_DIR: Path
    _DATABASE_PATH: Path

    def __new__(cls) -> Settings:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            backend_dir = Path(__file__).resolve().parents[2]
            cls._instance._BASE_DIR = backend_dir
            cls._instance._PROJECT_DIR = backend_dir.parent
            cls._instance._UPLOAD_DIR = backend_dir / "uploads"
            cls._instance._DATABASE_PATH = backend_dir / "escroweye.sqlite3"
        return cls._instance

    @property
    def BASE_DIR(self) -> Path:
        return self._BASE_DIR

    @property
    def PROJECT_DIR(self) -> Path:
        return self._PROJECT_DIR

    @property
    def UPLOAD_DIR(self) -> Path:
        return self._UPLOAD_DIR

    @property
    def DATABASE_URL(self) -> str:
        return os.getenv("ESCROWEYE_DATABASE_URL", "")

    @property
    def DATABASE_PATH(self) -> Path:
        return self._DATABASE_PATH

    @property
    def SECRET(self) -> str:
        return os.getenv("ESCROWEYE_SECRET", "escroweye-dev-secret")

    @property
    def AUTH_REQUIRE_SIGNATURE(self) -> bool:
        return os.getenv("ESCROWEYE_AUTH_REQUIRE_SIGNATURE", "false").lower() in {"1", "true", "yes", "on"}

    @property
    def OPENROUTER_API_KEY(self) -> str | None:
        return os.getenv("OPENROUTER_API_KEY")

    @property
    def OPENROUTER_MODEL(self) -> str:
        return os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")

    @property
    def HEDERA_OPERATOR_ID(self) -> str | None:
        return os.getenv("HEDERA_OPERATOR_ID")

    @property
    def HEDERA_OPERATOR_KEY(self) -> str | None:
        return os.getenv("HEDERA_OPERATOR_KEY")

    @property
    def HEDERA_HCS_TOPIC_ID(self) -> str | None:
        return os.getenv("HEDERA_HCS_TOPIC_ID")

    @property
    def HEDERA_HCS_REQUIRE_REAL(self) -> bool:
        return os.getenv("HEDERA_HCS_REQUIRE_REAL", "").lower() in {"1", "true", "yes", "on"}

    @property
    def IPFS_REQUIRE_REAL(self) -> bool:
        return os.getenv("IPFS_REQUIRE_REAL", "").lower() in {"1", "true", "yes", "on"}

    @property
    def PINATA_JWT(self) -> str | None:
        return os.getenv("PINATA_JWT")

    @property
    def PINATA_API_URL(self) -> str:
        return os.getenv("PINATA_API_URL", "https://api.pinata.cloud/pinning/pinFileToIPFS")

    @property
    def PINATA_GATEWAY_URL(self) -> str:
        return os.getenv("PINATA_GATEWAY_URL", "https://gateway.pinata.cloud")

    @property
    def X402_REQUIRE_REAL(self) -> bool:
        return os.getenv("X402_REQUIRE_REAL", "").lower() in {"1", "true", "yes", "on"}

    @property
    def X402_FACILITATOR_URL(self) -> str | None:
        return os.getenv("X402_FACILITATOR_URL")

    @property
    def X402_NETWORK(self) -> str:
        return os.getenv("X402_NETWORK", "hedera:testnet")

    @property
    def X402_AMOUNT(self) -> str:
        return os.getenv("X402_AMOUNT", "10000000")

    @property
    def X402_ASSET(self) -> str:
        return os.getenv("X402_ASSET", "0.0.0")

    @property
    def X402_PAY_TO(self) -> str:
        return os.getenv("X402_PAY_TO", "0.0.7162784")

    @property
    def X402_MAX_TIMEOUT_SECONDS(self) -> int:
        return int(os.getenv("X402_MAX_TIMEOUT_SECONDS", "180"))

    @property
    def X402_FEE_PAYER(self) -> str:
        return os.getenv("X402_FEE_PAYER", "0.0.7162784")

    @property
    def X402_FACILITATOR(self) -> str:
        return os.getenv("X402_FACILITATOR", "blocky402-mock")

    @property
    def LOG_LEVEL(self) -> str:
        return os.getenv("ESCROWEYE_LOG_LEVEL", "DEBUG").upper()

    @property
    def LOG_DIR(self) -> str:
        return os.getenv("ESCROWEYE_LOG_DIR", "")

    @property
    def LOG_FORMAT(self) -> str:
        return os.getenv("ESCROWEYE_LOG_FORMAT", "text")

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return os.getenv("ESCROWEYE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174").split(",")

    def database_url(self) -> str:
        db_url = self.DATABASE_URL
        if db_url:
            return db_url
        return f"sqlite+aiosqlite:///{self.DATABASE_PATH}"

    def x402_payment_requirements(self) -> dict[str, object]:
        return {
            "scheme": "exact",
            "network": self.X402_NETWORK,
            "amount": self.X402_AMOUNT,
            "asset": self.X402_ASSET,
            "payTo": self.X402_PAY_TO,
            "maxTimeoutSeconds": self.X402_MAX_TIMEOUT_SECONDS,
            "extra": {"feePayer": self.X402_FEE_PAYER},
        }


settings = Settings()
