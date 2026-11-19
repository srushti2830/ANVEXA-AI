# Phase 12 Completion Report

## Implementation status

The human-review workflow has been implemented using existing `VerificationResult`,
`VerificationEvidence`, `EvidencePassage`, `ReviewHistory`, and Phase 10/11 metadata.

## Files created

- `backend/app/schemas/reviews.py`
- `backend/app/api/endpoints/reviews.py`
- `backend/app/services/human_review/human_review_service.py`
- `backend/tests/test_human_review.py`
- `backend/migrations/versions/20261119_0009_phase12_human_review_workflow.py`
- `backend/docs/phase12_human_review.md`
- `PHASE12_COMPLETION_REPORT.md`

## Files modified

- `backend/app/models/enums.py`
- `backend/app/models/__init__.py`
- `backend/app/models/verification.py`
- `backend/app/services/human_review/__init__.py`
- `backend/app/services/verdict_classifier/verdict_classifier.py`
- `backend/app/api/router.py`

## Existing models reused

- `VerificationResult`
- `VerificationEvidence`
- `EvidencePassage`
- `ResearchSource`
- `ReviewHistory`
- `Claim`
- `Document`
- `DocumentVersion`
- `User`

No duplicate verification or review table was created.

## Database changes

Migration `20261119_0009_phase12_human_review_workflow.py` adds:

- `review_status` to `VerificationResult`
- `assigned_reviewer_id` to `VerificationResult`
- `review_requested_at` to `VerificationResult`
- `REQUEST_INVESTIGATION` to `ReviewAction`
- Reviewer status and investigation foreign-key/index support

Existing records receive the migration default `pending` review status.

## API endpoints

- `GET /api/v1/reviews/queue`
- `GET /api/v1/reviews/{review_id}`
- `POST /api/v1/reviews/{review_id}/submit`
- `POST /api/v1/reviews/{review_id}/request-investigation`
- `GET /api/v1/reviews/{review_id}/history`
- `GET /api/v1/documents/{document_id}/reviews`

The existing Phase 11 `POST /api/v1/claims/{claim_id}/human-verdict` remains compatible.

## Security

- Authentication is required.
- Review endpoints require `REVIEWER` or `ADMIN`.
- Ordinary users are denied.
- Reviewer/admin document access is scoped through document ownership overrides.
- Reviewer identity is derived from the authenticated user.
- Submitted evidence IDs must belong to the verification result.
- Missing explanations and invalid verdicts are rejected.

## Workflow

Reviewers can queue, inspect, submit, resolve, or request further investigation. Human verdict
submission preserves the original AI verdict and creates a `ReviewHistory` record. Investigation
requests preserve the unresolved status and avoid duplicate requests.

## Tests

Complete backend suite:

- **171 passed**
- **0 failed**
- **0 skipped**

Focused human-review suite:

- **29 passed**
- **0 failed**
- **0 skipped**

Mocked tests cover queue/detail, submission, all six verdict options, missing explanations,
unauthorized/cross-user access, history, idempotency, investigation requests, and AI verdict
preservation.

## Not live-tested

- Live PostgreSQL migration
- Live Alembic upgrade/downgrade
- Live JWT reviewer/admin authentication
- Live document ownership across authenticated users
- Live API response serialization

## Known limitations

- Assignment is represented by `assigned_reviewer_id`; no separate assignment queue workflow exists.
- Review detail does not introduce editor-side React UI.
- Live provider behavior is not part of this workflow.
