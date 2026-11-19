from fastapi import APIRouter

from backend.app.api.endpoints.auth import router as auth_router
from backend.app.api.endpoints.health import router as health_router
from backend.app.api.endpoints.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
