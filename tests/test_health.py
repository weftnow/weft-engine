import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Environment, Settings
from src.main import create_app


async def test_health_and_documented_contract() -> None:
    settings = Settings(_env_file=None, environment=Environment.TEST)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "weft-engine"}
        schema = (await client.get("/openapi.json")).json()
        assert set(schema["paths"]) == {"/health"}
        assert (await client.get("/docs")).status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/redoc"])
async def test_production_does_not_expose_docs(path: str) -> None:
    settings = Settings(_env_file=None, environment=Environment.PRODUCTION, docs_enabled=False)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        assert (await client.get(path)).status_code == 404
        assert (await client.get("/health")).status_code == 200
