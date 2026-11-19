# Phase 7 - Citation Detection and Mapping

## Workflow

1. Require an authenticated document owner and a completed parsed document.
2. Read the latest `DocumentVersion` and its `DocumentPage` records.
3. Detect in-text citation markers and bibliography/reference entries.
4. Normalize markers without replacing the original marker text.
5. Match Phase 6 claims to detected markers or references on the same document version.
6. Persist explicit `ClaimCitation` relationships and return paginated results.

Repeated detection is idempotent. Existing citation and claim-citation rows are reused through
document-version and normalized-marker keys.

## Supported marker styles

- IEEE and numbered bracket markers: `[1]`, `[2, 4, 6]`
- APA and author-year parentheses: `(Smith et al., 2023)`
- Named author-year: `Smith and Jones (2022)`
- MLA-style author-year variants
- Vancouver numbered references

DOI strings found in parsed text or reference entries are captured as reference metadata. They are
not used to claim that a source supports a claim.

## Reference entries

The rule-based parser captures only fields evidenced in the reference text:

- Authors
- Publication year
- Publication title where identifiable
- Journal or conference name
- Volume
- Issue
- Page range
- DOI
- URL
- Original reference text
- Number or author-year normalized key

Missing fields remain `null`; the engine never invents bibliographic information.

## Mapping statuses

- `MATCHED`: one reference or marker is associated unambiguously.
- `UNMATCHED`: no usable match was found.
- `AMBIGUOUS`: the context is insufficient for one unique interpretation.
- `MULTIPLE_MATCHES`: more than one reference could match.
- `MISSING_REFERENCE`: a numbered citation has no corresponding reference entry.

Mapping indicates document traceability only. It does not determine citation support or truth.

## API testing

Authorize in Swagger, then call:

- `POST /api/v1/documents/{document_id}/detect-citations`
- `GET /api/v1/documents/{document_id}/citations?page=1&per_page=20`
- `GET /api/v1/claims/{claim_id}/citations`
- `GET /api/v1/documents/{document_id}/citation-mapping?page=1&per_page=20`
