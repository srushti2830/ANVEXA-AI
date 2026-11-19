# ANVEXA AI — Phase 5: Document Parsing and OCR

## Overview

Phase 5 adds real document text extraction to ANVEXA AI. It supports PDF files (via PyMuPDF), DOCX files (via python-docx), and scanned/image-based PDF pages (via Tesseract OCR + PyMuPDF rendering).

---

## Architecture

```
POST /api/v1/documents/{id}/parse
        │
        ▼
  parser_service.py          (orchestration, DB, status lifecycle)
        │
        ▼
  parser.py                  (unified router — detects format, invokes parser)
        │
   ┌────┴────┐
   ▼         ▼
pdf_parser  docx_parser
   │
   ▼ (if scanned pages detected)
ocr_service.py
   │
   ▼
text_cleaner.py              (whitespace, Unicode, header/footer removal)
```

---

## PDF Parsing (`pdf_parser.py`)

**Library:** PyMuPDF (`pymupdf`)

**How it works:**
1. Opens the PDF from raw bytes using `pymupdf.open(stream=data, filetype="pdf")`.
2. Checks if the PDF is encrypted. Attempts to authenticate with an empty password (common for print-restricted PDFs). Raises `ValueError` if authentication fails.
3. Iterates over every page (0-indexed), extracting text via `page.get_text("text")` which returns plaintext preserving paragraph breaks.
4. Detects scanned/image-based pages using a heuristic: a page is flagged as "needs OCR" if it contains images but fewer than 50 characters of extractable text.
5. Collects per-page metadata: char count, word count, dimensions, image presence, extraction method.
6. Returns a `ParsedDocument` dataclass with pages, metadata, OCR candidate list, and warnings.

**Handles:**
- Corrupted PDFs → raises `ValueError`
- Encrypted PDFs → tries empty password, fails with clear message
- Empty PDFs (0 pages) → raises `ValueError`
- Empty pages → warned, not silently dropped
- Pages with no text → flagged for OCR

---

## DOCX Parsing (`docx_parser.py`)

**Library:** python-docx

**How it works:**
1. Opens the DOCX from raw bytes using `DocxDocument(io.BytesIO(data))`.
2. Iterates over all paragraphs in document order:
   - Detects headings via style name (e.g. "Heading 1" → level 1).
   - Extracts heading text, level, and style name.
   - Non-heading paragraphs are recorded as plain blocks.
3. Extracts table content: cells joined by tabs, rows by newlines.
4. Since DOCX files lack physical page breaks, text is segmented into logical "pages" using a ~3000-character threshold.
5. Collects document-level metadata from core properties (title, author, subject, keywords).

**Handles:**
- Invalid/corrupted DOCX → raises `ValueError`
- Empty DOCX → returns single empty page with warning
- Missing core properties → silently skipped

---

## OCR Service (`ocr_service.py`)

**Libraries:** PyMuPDF (rendering), pytesseract, Pillow

**How it works:**
1. Checks that the `tesseract` binary is on `PATH` using `shutil.which()`.
2. For each specified page number:
   - Renders the PDF page to a PNG image at **300 DPI** using PyMuPDF's `page.get_pixmap()`.
   - Converts the pixmap to a PIL Image.
   - Runs `pytesseract.image_to_string()` to extract text.
   - Optionally runs `image_to_data()` to calculate average OCR confidence.
3. Returns `OCRResult` with per-page text, confidence scores, and warnings.

**Safety rules:**
- OCR text is **only** used if it produces **more characters** than the original PyMuPDF extraction. This prevents replacing valid extracted text with poor OCR output.
- Pages producing fewer than 20 OCR characters are warned as potentially blank.

---

## Installing Tesseract on Windows

1. Download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
2. Run the installer. The default path is `C:\Program Files\Tesseract-OCR`.
3. Add the installation directory to your system `PATH`:
   - Open **System Properties** → **Environment Variables**.
   - Edit the **Path** variable under **System variables**.
   - Add `C:\Program Files\Tesseract-OCR`.
4. Verify installation:
   ```
   tesseract --version
   ```
5. (Optional) Set `TESSERACT_CMD` environment variable if pytesseract cannot find it automatically:
   ```
   set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
   ```

> **Note:** If Tesseract is not installed, PDF parsing still works for text-based PDFs. Only scanned/image-based pages will show a warning that OCR is unavailable.

---

## Text Cleaner (`text_cleaner.py`)

**Operations performed:**
1. Unicode NFC normalization
2. Replace non-breaking spaces, zero-width spaces, BOM, line/paragraph separators
3. Tab-to-spaces conversion
4. Collapse multiple spaces to single space
5. Remove trailing spaces on each line
6. Collapse 3+ consecutive newlines to 2 (preserve paragraph breaks)
7. Remove standalone page-number lines (e.g. `— 42 —`)
8. Cross-page header/footer removal: lines appearing on 3+ pages at the top/bottom are stripped

**Preserves:**
- Numeric citations: `[1]`, `[1-3]`, `[1, 2]`
- Author-year citations: `(Smith et al., 2023)`
- DOI strings: `10.1234/...`
- Section headings
- Meaningful punctuation

---

## Unified Parser (`parser.py`)

The entry point that:
1. Identifies file format by MIME type.
2. Routes to `parse_pdf()` or `parse_docx()`.
3. Runs OCR on scanned PDF pages (if Tesseract is available and enabled).
4. Applies text cleaning to all pages.
5. Returns `UnifiedParseResult` with:
   - `filename`, `file_type`, `extraction_method`
   - `total_pages`, `extracted_text`, `page_texts`
   - `paragraphs`, `headings`
   - `ocr_pages`, `ocr_applied`
   - `character_count`, `word_count`, `processing_duration_ms`
   - `status` (completed / completed_with_warnings / failed)
   - `warnings`, `errors`, `metadata`

---

## API Endpoints

### Parse a Document

```
POST /api/v1/documents/{document_id}/parse
Authorization: Bearer <token>
```

**Requires:** Valid JWT token. User must own the document.

**Behavior:**
1. Verifies document exists and belongs to the authenticated user.
2. Checks document is in `uploaded` or `failed` status (retries are allowed).
3. Transitions status: `UPLOADED` → `VALIDATING` → `PROCESSING` → `COMPLETED` (or `FAILED`).
4. Reads file bytes from storage.
5. Runs the unified parser.
6. Creates `DocumentVersion` and `DocumentPage` records.
7. Returns a summary with version ID, page count, extraction method, etc.

**Response (200):**
```json
{
  "document_id": "...",
  "filename": "paper.pdf",
  "file_type": "application/pdf",
  "version_id": "...",
  "version_number": 1,
  "total_pages": 12,
  "total_characters": 45230,
  "extraction_method": "pymupdf",
  "ocr_applied": false,
  "ocr_pages": [],
  "headings": [],
  "character_count": 45230,
  "word_count": 7380,
  "processing_duration_ms": 142,
  "processing_status": "completed",
  "warnings": [],
  "metadata": { ... }
}
```

### Retrieve Parsed Content

```
GET /api/v1/documents/{document_id}/parsed-content
Authorization: Bearer <token>
```

**Returns** the full extracted text, page-by-page content, OCR page list, and processing status for the latest parsed version.

---

## Testing Through Swagger

1. Start the server:
   ```
   cd backend
   uvicorn app.main:app --reload
   ```
2. Open `http://localhost:8000/docs` in your browser.
3. Register a user via `POST /api/v1/auth/register`.
4. Login via `POST /api/v1/auth/login` to get an access token.
5. Click **Authorize** and enter `Bearer <token>`.
6. Upload a document via `POST /api/v1/documents/upload`.
7. Copy the returned `document_id`.
8. Call `POST /api/v1/documents/{document_id}/parse`.
9. Call `GET /api/v1/documents/{document_id}/parsed-content` to retrieve extracted text.

---

## Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `422: Document parsing failed` | Corrupted, encrypted, or unsupported file | Upload a valid PDF or DOCX |
| `409: Document is in 'completed' state` | Document was already parsed | Re-parse is blocked for completed docs; re-upload if needed |
| `503: Unable to read document from storage` | File missing from disk | Re-upload the document |
| `404: Document not found` | Invalid document_id or wrong user | Check the document_id and ensure you own it |
| `404: Document has not been parsed yet` | Calling GET before POST parse | Call POST parse first |
| `OCR warning: Tesseract not installed` | Scanned pages found but Tesseract missing | Install Tesseract (see section above) |
| `PDF is encrypted and requires a password` | Password-protected PDF | Remove password protection before uploading |
