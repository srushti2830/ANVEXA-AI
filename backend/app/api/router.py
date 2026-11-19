from fastapi import APIRouter

from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.documents import router as documents_router
from app.api.endpoints.health import router as health_router
from app.api.endpoints.parsing import router as parsing_router
from app.api.endpoints.claims import router as claims_router
from app.api.endpoints.claims import claim_router
from app.api.endpoints.citations import document_router as citations_router
from app.api.endpoints.citations import claim_router as claim_citations_router
from app.api.endpoints.users import router as users_router
from app.api.endpoints.sources import document_router as sources_router
from app.api.endpoints.sources import claim_router as claim_sources_router
from app.api.endpoints.sources import source_router as research_sources_router
from app.api.endpoints.evidence import claim_router as claim_evidence_router
from app.api.endpoints.evidence import document_router as document_evidence_router
from app.api.endpoints.evidence import source_router as source_evidence_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(documents_router)
api_router.include_router(parsing_router)
api_router.include_router(claims_router)
api_router.include_router(claim_router)
api_router.include_router(citations_router)
api_router.include_router(claim_citations_router)
api_router.include_router(sources_router)
api_router.include_router(claim_sources_router)
api_router.include_router(research_sources_router)
api_router.include_router(claim_evidence_router)
api_router.include_router(document_evidence_router)
api_router.include_router(source_evidence_router)
