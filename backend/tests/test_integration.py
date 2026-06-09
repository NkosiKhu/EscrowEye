"""Basic integration tests to verify the merged EscrowEye codebase works."""
from __future__ import annotations

import pytest


class TestImports:
    """Verify all major modules import without errors."""

    def test_app_main_imports(self):
        from app.core.config import settings
        assert settings.DATABASE_PATH.name == "escroweye.sqlite3"

    def test_app_config_compat(self):
        from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL, UPLOAD_DIR
        assert UPLOAD_DIR.name == "uploads"

    def test_app_database_compat(self):
        from app.database import DB_PATH, now_iso, db
        assert DB_PATH.name == "escroweye.sqlite3"
        ts = now_iso()
        assert ts.endswith("Z")
        assert "T" in ts

    def test_agent_core_imports(self):
        from agent.graph import review_graph
        assert review_graph is not None

    def test_agent_service_imports(self):
        from agent.service import trigger_assistant, trigger_review
        import inspect
        assert inspect.iscoroutinefunction(trigger_assistant)
        assert inspect.iscoroutinefunction(trigger_review)

    def test_agent_tools_imports(self):
        from agent.tools import (
            check_funding,
            get_jobs, get_job, create_job,
            get_homes, create_home,
            place_bid, get_bids, award_bid,
            fund_escrow, mark_ready,
            send_message, get_messages,
            get_photos, associate_photo,
            confirm_job, dispute_job,
            set_agent_jwt,
        )
        assert get_jobs.name == "get_jobs"

    def test_infrastructure_imports(self):
        from app.infrastructure.database import get_db, get_session, create_tables
        import inspect
        assert inspect.iscoroutinefunction(create_tables)

    def test_infrastructure_models(self):
        from app.infrastructure.models import User, Home, Job, Bid, Message, Photo, Room
        assert User.__tablename__ == "users"

    def test_api_routes_imports(self):
        from app.api.routes.auth import create_auth_router
        from app.api.routes.jobs import create_jobs_router
        from app.api.routes.homes import create_homes_router
        from app.api.routes.proof import create_proof_router
        from app.api.routes.escrow import create_escrow_router
        from app.api.routes.quotes import create_quotes_router
        from app.api.routes.service_requests import create_service_requests_router
        from app.api.routes.audit import create_audit_router
        from app.api.routes.ai_validation import create_ai_validation_router
        from app.api.routes.earnings import create_earnings_router
        assert callable(create_auth_router)

    def test_services_imports(self):
        from app.services.escrow import EscrowService
        from app.services.hedera_client import get_client, get_operator_id, get_operator_key
        from app.services.dev_mode import is_dev_mode, get_dev_private_key, get_dev_account_id, auto_pay_x402
        from app.services.job_service import JobService
        from app.services.auth_service import AuthService
        from app.services.proof_service import ProofService
        from app.services.marketplace import SERVICE_CATEGORIES
        assert callable(EscrowService)
        assert callable(get_client)

    def test_devmode_utils(self):
        from app.services.dev_mode import is_dev_mode, get_dev_private_key, get_dev_account_id
        assert callable(is_dev_mode)
        assert callable(get_dev_private_key)
        assert callable(get_dev_account_id)


class TestAppFactory:
    """Verify the FastAPI app can be created and its routes registered."""

    @pytest.fixture
    def app(self):
        from app.main import app
        return app

    @pytest.mark.asyncio
    async def test_root_endpoint(self, app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "EscrowEye"

    @pytest.mark.asyncio
    async def test_health_endpoints(self, app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.get("/health")
            resp2 = await client.get("/api/health")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json() == {"status": "healthy"}
        assert resp2.json() == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_cors_headers_present(self, app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.options("/", headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_route_returns_404(self, app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/nonexistent")
        assert resp.status_code == 404


class TestAgentTools:
    """Verify agent tools can be invoked (without server)."""

    def test_tool_names(self):
        from agent.tools import (
            check_funding,
            get_jobs, get_job, create_job,
            get_homes, create_home,
            place_bid, get_bids, award_bid,
            fund_escrow, mark_ready,
            send_message, get_messages,
            get_photos, associate_photo,
            confirm_job, dispute_job,
        )
        names = {t.name for t in [
            check_funding,
            get_jobs, get_job, create_job,
            get_homes, create_home,
            place_bid, get_bids, award_bid,
            fund_escrow, mark_ready,
            send_message, get_messages,
            get_photos, associate_photo,
            confirm_job, dispute_job,
        ]}
        assert names == {
            "check_funding",
            "get_jobs", "get_job", "create_job",
            "get_homes", "create_home",
            "place_bid", "get_bids", "award_bid",
            "fund_escrow", "mark_ready",
            "send_message", "get_messages",
            "get_photos", "associate_photo",
            "confirm_job", "dispute_job",
        }

    def test_agent_jwt_context_var(self):
        from agent.tools import set_agent_jwt, get_agent_jwt
        set_agent_jwt("test-token")
        assert get_agent_jwt() == "test-token"
        set_agent_jwt("")
        assert get_agent_jwt() == ""


class TestServiceRoutes:
    """Verify service modules produce valid payloads."""

    @pytest.mark.asyncio
    async def test_marketplace_service_categories(self):
        from app.services.marketplace import SERVICE_CATEGORIES
        assert isinstance(SERVICE_CATEGORIES, list)
        assert len(SERVICE_CATEGORIES) >= 7
        ids = {c["id"] for c in SERVICE_CATEGORIES}
        assert ids == set(range(1, len(SERVICE_CATEGORIES) + 1))

    def test_signature_verifier_imports(self):
        from app.services.signature_verifier import signature_required, challenge_message, verify_wallet_signature
        assert callable(signature_required)
        assert callable(challenge_message)
        assert callable(verify_wallet_signature)
