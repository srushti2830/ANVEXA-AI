from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description="Evidence-traceable academic document verification API.",
    )
    application.include_router(api_router, prefix=app_settings.api_v1_prefix)

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
