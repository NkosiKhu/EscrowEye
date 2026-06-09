from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.core.config import settings
from app.infrastructure.database import create_tables, get_session, reset_engine


def make_client(tmp_path: Path) -> TestClient:
    """Create a TestClient with an isolated async SQLite database."""
    db_path = tmp_path / "escroweye-test.sqlite3"
    os.environ["ESCROWEYE_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    reset_engine()

    async def _setup():
        await create_tables()
        from app.main import seed_service_categories
        async with get_session() as session:
            await seed_service_categories(session)

    asyncio.run(_setup())
    return TestClient(main.app)


def login(client: TestClient, account: str, role: str) -> str:
    challenge = client.post("/api/auth/challenge", json={"hedera_account_id": account})
    assert challenge.status_code == 200
    nonce = challenge.json()["nonce"]
    response = client.post(
        "/api/auth/login",
        json={
            "hedera_account_id": account,
            "hedera_public_key": f"pub-{account}",
            "signature": f"sig-{nonce}",
            "nonce": nonce,
            "user_type": role,
        },
    )
    assert response.status_code == 200
    return response.json()["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
