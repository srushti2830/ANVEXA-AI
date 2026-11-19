# Phase 10 - AI Claim Verification

## Workflow

1. Load the exact claim, location, category, citation markers, and mapped references.
2. Retrieve Phase 9 evidence passages linked by source or claim.
3. If no evidence exists, create a `NEEDS_REVIEW` result and require human review.
4. Send claim and evidence to Gemini with a fixed evidence-grounded prompt.
5. Validate Pydantic output and ensure every referenced evidence ID exists in the supplied set.
6. Persist a historical `VerificationResult` and supporting/contradicting `VerificationEvidence` links.
7. Repeated completed or needs-review processing returns the latest matching verification without duplication.
8. Failed Gemini processing is persisted as `FAILED` and can be retried safely.

## Verdict classes

- `SUPPORTED`
- `PARTLY_SUPPORTED`
- `UNSUPPORTED`
- `CONTRADICTORY`
- `POSSIBLY_OUTDATED`
- `NEEDS_REVIEW`

Semantic similarity is never treated as proof. Gemini must evaluate exact meaning, population, numbers,
causality, scope, temporal relevance, conflicting evidence, and limitations.

## Prompt

The prompt version is `phase10-v1`. It explicitly prohibits fabricated sources or evidence and requires
every conclusion involving evidence to use IDs supplied in the prompt.

## Confidence

Confidence is an extraction/analysis indicator, not a probability that a claim is true. Scores use:

- 0.75–1.00: high
- 0.45–0.74: medium
- 0.00–0.44: low

Low quality or missing evidence sets the result to low confidence or `NEEDS_REVIEW`.

## API testing

Authorize in Swagger, then call:

- `POST /api/v1/claims/{claim_id}/verify`
- `POST /api/v1/documents/{document_id}/verify`
- `GET /api/v1/claims/{claim_id}/verification`
- `GET /api/v1/documents/{document_id}/verification`
- `GET /api/v1/claims/{claim_id}/verification-history`
