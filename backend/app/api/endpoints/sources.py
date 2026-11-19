"""Research source retrieval API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.sources import (
    DocumentSourceListResponse,
    ResearchSourceResponse,
    SourceRetrievalResponse,
)
from app.services.source_retriever.source_retriever import (
    get_source,
    list_claim_sources,
    list_document_sources,
    retrieve_sources,
)

document_router = APIRouter(prefix="/documents", tags=["sources"])
claim_router = APIRouter(tags=["sources"])
source_router = APIRouter(prefix="/sources", tags=["sources"])


@document_router.post(
    "/{document_id}/retrieve-sources",
    response_model=SourceRetrievalResponse,
    summary="Retrieve research source metadata for a parsed document",
)
def retrieve_document_sources(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return retrieve_sources(document_id, current_user, db)


@document_router.get(
    "/{document_id}/sources",
    response_model=DocumentSourceListResponse,
    summary="List retrieved sources associated with a document",
)
def get_document_sources(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_document_sources(document_id, current_user, db, page, per_page)


@source_router.get(
    "/{source_id}",
    response_model=ResearchSourceResponse,
    summary="Get one retrieved research source",
)
def get_research_source(
    source_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_source(source_id, current_user, db)


@claim_router.get(
    "/claims/{claim_id}/sources",
    response_model=list[ResearchSourceResponse],
    summary="List retrieved research sources associated with a claim",
)
def get_claim_sources(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_claim_sources(claim_id, current_user, db)
