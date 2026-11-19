# Phase 11 - Final Verdict Classification

## Separation of concerns

Phase 10 remains responsible for AI analysis. Its `verdict`, explanation, structured fields,
supporting and contradicting evidence IDs, limitations, confidence, and human-review flag are
preserved unchanged.

Phase 11 adds a deterministic final verdict classification to the existing `VerificationResult`.
It does not call Gemini.

## Input

The classifier consumes:

- The latest `VerificationResult`
- `verification_status`
- AI `verdict`
- `structured_analysis`
- Supporting and contradicting evidence IDs
- Limitations and unresolved questions
- Confidence and human-review flag

## Output

The response contains:

- `verification_result_id`
- `claim_id`
- `ai_verdict`
- `final_verdict`
- `classification_method`
- `classification_reason`
- `classification_confidence`
- Supporting evidence IDs
- Contradicting evidence IDs
- Limitations
- Unresolved questions
- Human-review flag
- Classification timestamp

## Categories

- `supported`
- `partly_supported`
- `unsupported`
- `contradictory`
- `possibly_outdated`
- `needs_review`

## Human review

Reviewer or administrator roles can submit a human verdict. The `ReviewHistory` model records the
original Phase 10/Phase 11 result and final human verdict. The final verdict fields on
`VerificationResult` are updated without overwriting verification history.

## API testing

- `POST /api/v1/claims/{claim_id}/classify-verdict`
- `GET /api/v1/claims/{claim_id}/verdict`
- `POST /api/v1/documents/{document_id}/classify-verdicts`
- `GET /api/v1/documents/{document_id}/verdicts`
- `POST /api/v1/claims/{claim_id}/human-verdict`
