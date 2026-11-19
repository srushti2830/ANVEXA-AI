# Phase 14 API Integration Matrix

| Frontend page/component | Endpoint | Method | Request | Response | Authentication | Status |
|---|---|---|---|---|---|---|
| Registration | `/api/v1/auth/register` | POST | RegisterRequest | UserResponse | Public | Integrated |
| Login | `/api/v1/auth/login` | POST | LoginRequest | TokenResponse | Public | Integrated |
| Refresh | `/api/v1/auth/refresh` | POST | RefreshTokenRequest | TokenResponse | Public | Integrated |
| Logout | `/api/v1/auth/logout` | POST | RefreshTokenRequest | MessageResponse | Public token action | Integrated |
| Current account | `/api/v1/auth/me` | GET | None | UserResponse | Bearer | Integrated |
| Dashboard analytics | `/api/v1/analytics/overview` | GET | None | AnalyticsOverviewResponse | Bearer | Integrated |
| Recent documents | `/api/v1/documents` | GET | Pagination/filter query | DocumentListResponse | Bearer | Integrated |
| Upload document | `/api/v1/documents/upload` | POST | multipart PDF/DOCX | DocumentUploadResponse | Bearer | Integrated |
| Document detail | `/api/v1/documents/{document_id}` | GET | Path ID | DocumentResponse | Bearer/owner | Integrated |
| Document delete | `/api/v1/documents/{document_id}` | DELETE | Path ID | Delete response | Bearer/owner | Backend available; not exposed in main UI |
| Parse | `/api/v1/documents/{document_id}/parse` | POST | Path ID | ParseResultResponse | Bearer/owner | Integrated |
| Extract claims | `/api/v1/documents/{document_id}/extract-claims` | POST | Path ID | ClaimExtractionResponse | Bearer/owner | Integrated |
| Detect citations | `/api/v1/documents/{document_id}/detect-citations` | POST | Path ID | CitationDetectionResponse | Bearer/owner | Integrated |
| Retrieve sources | `/api/v1/documents/{document_id}/retrieve-sources` | POST | Path ID | SourceRetrievalResponse | Bearer/owner | Integrated |
| Extract evidence | `/api/v1/documents/{document_id}/extract-evidence` | POST | Path ID | Document evidence response | Bearer/owner | Integrated |
| Verify document | `/api/v1/documents/{document_id}/verify` | POST | Path ID | DocumentVerificationResponse | Bearer/owner | Integrated |
| Classify verdicts | `/api/v1/documents/{document_id}/classify-verdicts` | POST | Path ID | Classification summary | Bearer/owner | Integrated |
| Claim list | `/api/v1/documents/{document_id}/claims` | GET | Pagination | ClaimListResponse | Bearer/owner | Integrated |
| Citation list | `/api/v1/documents/{document_id}/citations` | GET | Pagination | DocumentCitationListResponse | Bearer/owner | Integrated |
| Source list | `/api/v1/documents/{document_id}/sources` | GET | Pagination | DocumentSourceListResponse | Bearer/owner | Integrated |
| Claim detail | `/api/v1/claims/{claim_id}` | GET | Path ID | ClaimResponse | Bearer/owner | Integrated |
| Claim evidence | `/api/v1/claims/{claim_id}/evidence` | GET | Pagination | ClaimEvidenceResponse | Bearer/owner | Integrated |
| Claim sources | `/api/v1/claims/{claim_id}/sources` | GET | Path ID | Research source list | Bearer/owner | Integrated |
| Claim verification | `/api/v1/claims/{claim_id}/verification` | GET | Path ID | VerificationResponse | Bearer/owner | Integrated |
| Claim verdict | `/api/v1/claims/{claim_id}/verdict` | GET | Path ID | VerdictClassificationResponse | Bearer/owner | Integrated |
| Review queue | `/api/v1/reviews/queue` | GET | Filters/pagination | ReviewQueueResponse | Reviewer/admin | Integrated |
| Review detail | `/api/v1/reviews/{review_id}` | GET | Path ID | ReviewDetailResponse | Reviewer/admin/ownership | Integrated |
| Review submit | `/api/v1/reviews/{review_id}/submit` | POST | ReviewSubmitRequest | ReviewHistory item | Reviewer/admin/ownership | Integrated |
| Investigation | `/api/v1/reviews/{review_id}/request-investigation` | POST | ReviewInvestigationRequest | ReviewHistory item | Reviewer/admin/ownership | Integrated |
| Review history | `/api/v1/reviews/{review_id}/history` | GET | Pagination | ReviewHistoryResponse | Reviewer/admin/ownership | Integrated |
| Document reviews | `/api/v1/documents/{document_id}/reviews` | GET | Pagination | Review list | Reviewer/admin/ownership | Integrated |
| Document report | `/api/v1/documents/{document_id}/report` | GET | Path ID | DocumentReportResponse | Bearer/owner | Integrated |
| PDF report | `/api/v1/documents/{document_id}/report/pdf` | GET | Path ID | application/pdf | Bearer/owner | Integrated; live download unverified |
| JSON report | `/api/v1/documents/{document_id}/report/json` | GET | Path ID | application/json | Bearer/owner | Integrated; live download unverified |
| Document analytics | `/api/v1/analytics/documents/{document_id}` | GET | Path ID | DocumentAnalyticsResponse | Bearer/owner | Integrated |
| Claim report | `/api/v1/claims/{claim_id}/report` | GET | Path ID | ClaimReportResponse | Bearer/owner | Integrated |

No essential missing API was identified for the implemented frontend scope.
