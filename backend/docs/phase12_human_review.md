# Phase 12 - Human Review Workflow

## Review lifecycle

Each verification result is the stable review identifier. The review lifecycle is:

- `pending`
- `in_review`
- `resolved`
- `investigation_requested`

The queue includes verification results marked for human review or `NEEDS_REVIEW`, unless a status
filter is supplied. Reviewers can filter by document, verdict, status, and confidence.

## Review detail

The detail response preserves:

- Original claim and document location
- Phase 10 AI verdict and explanation
- Final/Phase 11 verdict
- Supporting and contradicting evidence passages
- Source title, DOI, URL, publication year, section, and page metadata
- Limitations and unresolved questions
- Structured Phase 10 analysis

## Submission

Human verdict submission requires a reviewer explanation of at least ten characters. Optional notes
are appended to the same review record. Evidence IDs must belong to the verification result.

Submitting again for an already resolved review is idempotent and returns the existing action.
Investigation requests are idempotent as well.

## History

`ReviewHistory` remains the append-only audit record. It records reviewer identity, original AI
verdict, human verdict or investigation request, timestamp, comment, resolution state, and optional
additional evidence.

## Security

Only reviewer and administrator roles can access review routes. Document ownership checks allow
reviewer/admin roles and deny ordinary users.
