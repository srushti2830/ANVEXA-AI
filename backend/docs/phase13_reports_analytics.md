# Phase 13 - Reports and Analytics

## Report workflow

Reports are assembled from existing database records:

- Document and document-version metadata
- Phase 6 claims
- Phase 7 citations and mapped references
- Phase 8 research sources
- Phase 9 evidence passages
- Phase 10 verification analysis
- Phase 11 final classification
- Phase 12 human-review history

The original AI verdict remains separate from a human-reviewed or final verdict. Historical review
records are never replaced.

## Analytics

Analytics are computed by database queries and counts:

- Documents uploaded and processed
- Claims extracted
- Citations detected
- Sources retrieved
- Evidence passages extracted
- Claims verified
- Final-verdict distribution
- Human-review completion rate
- Claims awaiting review
- Claims requiring investigation

## Exports

- JSON export is returned as a structured downloadable response.
- PDF export uses ReportLab and contains an executive summary, verdict statistics, claim details,
  evidence traceability, limitations, and a non-certification disclaimer.

No report is described as peer-reviewed or scientifically certified.
