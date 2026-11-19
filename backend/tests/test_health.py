import asyncio

from fastapi import FastAPI
import httpx

from app.core.config import Settings
from app.main import create_app


def get_response(app: FastAPI, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def test_health_endpoint_returns_ok() -> None:
    response = get_response(create_app(Settings()), "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_documents_health_endpoint() -> None:
    app = create_app(Settings())
    docs_response = get_response(app, "/docs")
    response = get_response(app, "/openapi.json")

    assert docs_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ANVEXA AI API"
    assert "/health" in response.json()["paths"]


def test_settings_read_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("ANVEXA_APP_NAME", "Test API")

    assert Settings().app_name == "Test API"
