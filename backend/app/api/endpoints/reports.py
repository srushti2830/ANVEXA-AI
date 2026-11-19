"""Report and analytics API endpoints."""

from __future__ import annotations

from json import dumps
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models.document import Document
from app.models.enums import ProcessingStatus, ReportFormat
from app.models.user import User
from app.models.verification import Report
from app.schemas.reports import (
    AnalyticsOverviewResponse,
    ClaimReportResponse,
    DocumentAnalyticsResponse,
    DocumentReportResponse,
)
from app.services.report_generator.report_service import (
    build_claim_report,
    build_document_analytics,
    build_document_report,
    build_overview_analytics,
    generate_pdf_report,
)

document_router = APIRouter(prefix="/documents", tags=["reports"])
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])
claims_router = APIRouter(prefix="/claims", tags=["reports"])


@document_router.get(
    "/{document_id}/report",
    response_model=DocumentReportResponse,
)
def get_document_report(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_document_report(document_id, current_user, db)


@document_router.get(
    "/{document_id}/report/pdf",
)
def get_document_pdf_report(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = build_document_report(document_id, current_user, db)
    try:
        data = generate_pdf_report(report)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="PDF report generation is unavailable") from exc
    document = db.get(Document, document_id)
    version = None
    if document is not None:
        from sqlalchemy import select
        from app.models.document import DocumentVersion

        version = db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        ).scalar_one_or_none()
    if document is not None and version is not None:
        db.add(Report(
            owner_id=current_user.id,
            document_id=document.id,
            document_version_id=version.id,
            format=ReportFormat.PDF,
            status=ProcessingStatus.COMPLETED,
            storage_key=None,
            generated_at=report["generated_at"],
        ))
        db.commit()
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="document-{document_id}-report.pdf"',
        },
    )


@document_router.get(
    "/{document_id}/report/json",
)
def get_document_json_report(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = build_document_report(document_id, current_user, db)
    document = db.get(Document, document_id)
    version = None
    if document is not None:
        from sqlalchemy import select
        from app.models.document import DocumentVersion

        version = db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        ).scalar_one_or_none()
    if document is not None and version is not None:
        db.add(Report(
            owner_id=current_user.id,
            document_id=document.id,
            document_version_id=version.id,
            format=ReportFormat.CSV,
            status=ProcessingStatus.COMPLETED,
            generated_at=report["generated_at"],
        ))
        db.commit()
    return Response(
        content=dumps(report, default=str, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="document-{document_id}-report.json"',
        },
    )


@analytics_router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
)
def get_analytics_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_overview_analytics(current_user, db)


@analytics_router.get(
    "/documents/{document_id}",
    response_model=DocumentAnalyticsResponse,
)
def get_document_analytics(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_document_analytics(document_id, current_user, db)


@claims_router.get(
    "/{claim_id}/report",
    response_model=ClaimReportResponse,
)
def get_claim_report(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_claim_report(claim_id, current_user, db)
