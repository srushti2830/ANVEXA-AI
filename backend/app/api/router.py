from fastapi import APIRouter

from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.documents import router as documents_router
from app.api.endpoints.health import router as health_router
from app.api.endpoints.parsing import router as parsing_router
from app.api.endpoints.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(documents_router)
api_router.include_router(parsing_router)
