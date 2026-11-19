import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.database.health import check_database_health

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health/database", tags=["system"])
def database_health() -> dict[str, str]:
    try:
        health = check_database_health()
    except (ImportError, RuntimeError, SQLAlchemyError) as error:
        logger.warning(
            "Database health check failed (%s)",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "database": "unavailable",
                "pgvector": "unknown",
            },
        ) from error

    if not health.pgvector_available:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "database": "ok",
                "pgvector": "unavailable",
            },
        )

    return {
        "status": "ok",
        "database": "ok",
        "pgvector": "available",
    }
