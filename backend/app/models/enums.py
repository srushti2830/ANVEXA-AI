from enum import Enum

from sqlalchemy import Enum as SQLAlchemyEnum


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class RetrievalStatus(str, Enum):
    PENDING = "pending"
    METADATA_ONLY = "metadata_only"
    FULL_TEXT_AVAILABLE = "full_text_available"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class ClaimType(str, Enum):
    NUMERICAL = "numerical"
    STATISTICAL = "statistical"
    COMPARATIVE = "comparative"
    CAUSAL = "causal"
    DESCRIPTIVE = "descriptive"
    TEMPORAL = "temporal"
    OTHER = "other"


class CitationStyle(str, Enum):
    NUMERIC = "numeric"
    AUTHOR_YEAR = "author_year"
    SUPERSCRIPT = "superscript"
    UNKNOWN = "unknown"


class SourceVersionType(str, Enum):
    PUBLISHED = "published"
    PREPRINT = "preprint"
    ACCEPTED_MANUSCRIPT = "accepted_manuscript"
    UNKNOWN = "unknown"


class Verdict(str, Enum):
    SUPPORTED = "supported"
    PARTLY_SUPPORTED = "partly_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTORY = "contradictory"
    POSSIBLY_OUTDATED = "possibly_outdated"
    NEEDS_REVIEW = "needs_review"


class ConfidenceLabel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceRelation(str, Enum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    NEUTRAL = "neutral"


class ReferenceIssueType(str, Enum):
    BROKEN_DOI = "broken_doi"
    METADATA_MISMATCH = "metadata_mismatch"
    UNRELATED_REFERENCE = "unrelated_reference"
    RETRACTED_SOURCE = "retracted_source"
    DUPLICATE_REFERENCE = "duplicate_reference"
    UNSUPPORTED_STATISTIC = "unsupported_statistic"
    POSSIBLY_FABRICATED = "possibly_fabricated"
    OTHER = "other"


class IssueCertainty(str, Enum):
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"


class ReviewAction(str, Enum):
    ACCEPT_AI = "accept_ai"
    REJECT_AI = "reject_ai"
    CHANGE_VERDICT = "change_verdict"
    RESOLVE = "resolve"
    REOPEN = "reopen"


class ReportFormat(str, Enum):
    PDF = "pdf"
    CSV = "csv"


class ProcessingJobType(str, Enum):
    PARSE_DOCUMENT = "parse_document"
    EXTRACT_CLAIMS = "extract_claims"
    DETECT_CITATIONS = "detect_citations"
    RETRIEVE_SOURCES = "retrieve_sources"
    PROCESS_EVIDENCE = "process_evidence"
    VERIFY_CLAIMS = "verify_claims"
    GENERATE_REPORT = "generate_report"


class ProcessingStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def enum_column(enum_class: type[Enum], name: str) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
    )
