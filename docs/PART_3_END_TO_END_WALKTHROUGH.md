# Part 3: End-to-End Walkthrough of a Realistic User Story

This document walks through one complete, realistic user scenario from start to finish. It connects the frontend user interface, REST APIs, Celery background tasks, PDF extraction pipelines, database models, question selection algorithms, and stateless PDF rendering engines into a unified view of the **TestSeries** application.

---

## Scenario Overview

* **Persona**: A CA Final educator / student creating a specialized practice test series for **CA Final - Financial Reporting (FR)**.
* **Goal**:
  1. Set up the syllabus for **Financial Reporting** with standard accounting chapters.
  2. Upload an official ICAI Revision Test Paper (**RTP May 2026**).
  3. Let the extraction pipeline process questions, answers, financial tables, formulas, and marks in the background.
  4. Review and refine extracted questions on the Review page, fixing chapter mappings and creating a new chapter inline.
  5. Generate a targeted 5-question RTP practice test covering specific accounting standards.
  6. Download the formatted **Question Paper PDF** and its companion **Suggested Answers PDF**.

---

## Step-by-Step System Execution

```
+---------------------------------------------------------------------------------------------------------------+
|                                      END-TO-END EXECUTION LIFECYCLE                                           |
+---------------------------------------------------------------------------------------------------------------+
| 1. SUBJECT SETUP          2. UPLOAD PAPER          3. ASYNC EXTRACTION       4. REVIEW & CORRECTION          |
| [Subjects.jsx]            [Upload.jsx]             [Celery / Worker]         [Review.jsx]                    |
| - Create Subject          - Drop PDF file          - Load PyMuPDF            - Inspect extracted questions   |
| - Add Chapters            - Smart detect month/yr  - Table & formula crops   - Edit question & answer text   |
| - Contiguous ordering     - POST /documents/upload - Regex hierarchy parsing - Inline create new chapter     |
|                           - Redirect /processing   - Match Q&A canonical     - PATCH /questions/:id          |
+---------------------------------------------------------------------------------------------------------------+
                                                                 |
                                                                 v
+---------------------------------------------------------------------------------------------------------------+
| 5. CONFIGURE GENERATOR                 6. DOWNLOAD QUESTION PAPER               7. DOWNLOAD ANSWER SHEET      |
| [Generate.jsx]                         [Generate.jsx -> pdf_renderer.py]        [Generate.jsx -> pdf_renderer]|
| - Select Subject & RTP Module          - POST /generate/question-paper/         - POST /generate/answer-sheet/|
| - Filter chapters & question count     - Fetch QuestionGroup DTOs by IDs        - Reuses identical group IDs  |
| - Debounced POST /generate/preview/    - Deduplicate shared case study context  - Keeps 1:1 question order    |
| - 100-attempt randomized selection     - Convert HTML to PDF via xhtml2pdf      - Omits context, keeps notes  |
| - Frontend caches root_question_ids    - Browser triggers .pdf download         - Browser triggers .pdf download|
+---------------------------------------------------------------------------------------------------------------+
```

---

### Step 1: Subject & Chapter Setup

1. **User Action**: The user opens the web app, navigates to the **Subjects** page (`/subjects`), and clicks **Add Subject**.
2. **Frontend Interaction** (`frontend/src/pages/Subjects.jsx`):
   * User enters Subject Name: `"Financial Reporting"`, Exam Level: `"Final"`.
   * Clicks **Save**.
   * Dispatches `subjectService.createSubject({ name: "Financial Reporting", exam_level: "Final" })`.
3. **API & Backend Processing** (`backend/apps/syllabus/`):
   * Request: `POST /api/v1/subjects/` -> `SubjectViewSet.create()`.
   * `SubjectSerializer.validate()` trims whitespace and verifies no subject named "Financial Reporting" exists under the "Final" level.
   * `Subject.save()` passes the name through `normalize_syllabus_name()`, applying canonical Title Case.
   * Inserted into database table `syllabus_subject`:
     `{ subject_id: 1, name: "Financial Reporting", exam_level: "Final", is_active: true }`.
4. **Adding Chapters**:
   * User clicks **Manage Chapters** on the Financial Reporting card.
   * Enters Chapter Name: `"Ind AS 115 - Revenue from Contracts with Customers"` -> Clicks **Add**.
   * Dispatches `POST /api/v1/subjects/1/chapters/`.
   * `ChapterViewSet.perform_create()` calculates `next_order = 1` and inserts record:
     `{ chapter_id: 101, subject_id: 1, chapter_name: "Ind AS 115 - Revenue from Contracts with Customers", chapter_order: 1 }`.
   * User repeats this to add:
     * `Ind AS 116 - Leases` (`chapter_id: 102`, `chapter_order: 2`)
     * `Ind AS 103 - Business Combinations` (`chapter_id: 103`, `chapter_order: 3`)

---

### Step 2: Uploading the ICAI RTP PDF

1. **User Action**: The user navigates to the **Upload Paper** page (`/upload`) and drags `CA_Final_FR_RTP_May_2026.pdf` (a 38-page document) into the drop zone.
2. **Frontend Validation & Auto-Detection** (`frontend/src/pages/Upload.jsx`):
   * `handleFile()` validates MIME type (`application/pdf`) and size (`< 100 MB`).
   * Smart regex inspects filename: detects `"may"` -> auto-sets `exam_month = "May"`; detects `"2026"` -> auto-sets `paper_year = 2026`.
   * User selects Subject: `"Financial Reporting"`, Document Type: `"RTP"`.
   * Clicks **Upload Paper**.
3. **API & Storage Handling** (`backend/apps/documents/`):
   * Dispatches `POST /api/v1/documents/upload/` via `multipart/form-data`.
   * `DocumentUploadSerializer` validates parameters and computes canonical title: `"Financial Reporting - RTP - May 2026"`.
   * `DocumentUploadView.perform_create()` saves file to disk: `media/documents/CA_Final_FR_RTP_May_2026.pdf`.
   * Creates `Document` record in SQLite:
     `{ document_id: 12, subject_id: 1, title: "Financial Reporting - RTP - May 2026", document_type: "RTP", paper_year: 2026, exam_month: "May", storage_path: "documents/CA_Final_FR_RTP_May_2026.pdf", extraction_status: "PENDING" }`.
   * Asynchronously queues Celery worker: `extract_document_task.delay(12)`.
   * API returns `HTTP 201 Created` with `{ document_id: 12, status: "PENDING" }`.
4. **Transition to Processing View**:
   * Frontend redirects to `/processing/12`.
   * `Processing.jsx` polls `GET /api/v1/documents/12/` and `GET /api/v1/extraction-logs/?document_id=12` every 2000ms.

---

### Step 3: Background Extraction Pipeline Execution

The Celery worker dequeues the task and executes the full pipeline:

1. **Isolation** (`ExtractionService.trigger_extraction`):
   * Copies PDF to sandbox: `backend/temp/12_a8b9c.pdf`.
   * Creates `ExtractionLog` with status `'PROCESSING'`.
   * Calls `extract_document(document, temp_file_path)`.
2. **Text, Margin & Visual Extraction** (`text_extractor.py`, `table_processing.py`):
   * `detect_headers_footers()` scans margins across all 38 pages, finding `"REVISION TEST PAPERS - MAY 2026"` on 36 pages. This string is registered to be stripped from question text.
   * `TableProcessor.process_document()` detects tables on pages 4, 8, 15, and 22:
     * A complex Balance Sheet on page 8 is rasterized into a high-res PNG crop: `media/table_crops/doc12_p8_y140.png`.
     * An HTML visual container `<div class="table-container" data-crop-path="/media/table_crops/doc12_p8_y140.png"><img src="/media/table_crops/doc12_p8_y140.png" /></div>` is embedded into page text.
   * Standalone formula drawing on page 15 is cropped to `media/formula_crops/doc12_p15_formula_y220.png`.
3. **Layout Detection & Section Slicing** (`layout_detector.py`, `section_splitter.py`):
   * Detects delimiter `"PART II - SUGGESTED ANSWERS"` at character offset `42,150`.
   * Layout is classified as `SECTION_WISE`.
   * `SectionSplitter` splits document into `q_part` (chars 0..42,150) and `a_part` (chars 42,150..end).
4. **Parsing & Hierarchy Matching** (`question_parser.py`, `answer_parser.py`, `answer_matcher.py`):
   * `QuestionParser` extracts questions:
     * Q1 (Comprehensive Case Study on Ind AS 115) with sub-questions (a) and (b).
     * Q2 (Ind AS 116 Lease computation) -> 16 Marks.
     * Q3 (Ind AS 103 Business Combinations) -> 14 Marks.
   * `AnswerParser` extracts matching answers and isolates nested Working Notes.
   * `AnswerMatcher` performs 1:1 matching on hierarchy path keys (`('1', 'a')`, `('1', 'b')`, `('2',)`).
5. **Enrichment & Database Persistence** (`chapter_mapper.py`, `marks_extractor.py`, `html_formatter.py`):
   * `ChapterMapper` detects `"Ind AS 115"` in the heading preceding Q1 and sets `chapter_id = 101`.
   * `MarksExtractor` extracts marks values (`16`, `14`, etc.).
   * `QuestionClassifier` classifies Q1 as `'PRACTICAL'`.
   * Inside `transaction.atomic()`: inserts all questions into `papers_question` table.
   * Sets `Document.extraction_status = 'COMPLETED'`, `ExtractionLog.status = 'COMPLETED'`.
   * Temporary sandbox file is cleaned up.
6. **Frontend Transition**:
   * `Processing.jsx` receives `extraction_status: "COMPLETED"`, displays a green checkmark, and automatically redirects to `/review/12`.

---

### Step 4: Verification, Review & Inline Chapter Creation

1. **Inspecting Extracted Questions** (`frontend/src/pages/Review.jsx`):
   * The page loads document details, questions (`GET /api/v1/questions/?document_id=12`), and extraction logs.
   * Stats bar shows: `Total: 18 | With Answers: 18 | Missing: 0 | Time: 4.82s | Matches: 18`.
2. **Editing Question 3**:
   * The user expands Question 3 and notices the chapter is unassigned because the PDF heading had a slight misspelling.
   * Clicks **Edit**.
   * In the chapter dropdown, the user wants to assign it to a new standard: `"Ind AS 102 - Share-based Payment"`.
3. **Inline Chapter Creation**:
   * User types `"Ind AS 102 - Share-based Payment"` into the SearchableSelect input.
   * The UI detects no existing match and displays: `"Create chapter 'Ind AS 102 - Share-based Payment'?"`.
   * User confirms -> Frontend calls `subjectService.createChapter(1, { chapter_name: "Ind AS 102 - Share-based Payment" })`.
   * `POST /api/v1/subjects/1/chapters/` creates Chapter `104`.
   * New chapter is added to the React state and auto-selected in the edit form.
4. **Submitting Edits**:
   * User clicks **Save Changes**.
   * Dispatches `PATCH /api/v1/questions/45/` with updated fields.
   * `QuestionSerializer` converts the updated question text to HTML (`text_to_html()`), saves the database record, and returns the updated question.
   * React updates the question card in state without page refresh.

---

### Step 5: Configuring Practice Paper Generation

1. **User Action**: The user navigates to the **Generate** page (`/generate`).
2. **Configuring Filters** (`frontend/src/pages/Generate.jsx`):
   * Paper Title: `"CA Final FR Mock Test - Series 1"`
   * Subject: Selects `"Financial Reporting"`
   * Module: Selects `"RTP"` (Revision Test Paper)
   * Question Count: Enters `5`
   * Chapter Multi-Select: Selects chips for:
     * `Ind AS 115 - Revenue from Contracts with Customers`
     * `Ind AS 116 - Leases`
     * `Ind AS 103 - Business Combinations`
3. **Debounced Preview Execution** (`backend/apps/papers/`):
   * 600ms after filter entry, `paperService.generatePreview(filters)` dispatches `POST /api/v1/generate/preview/`.
   * `GenerationFilterSerializer` validates module rules and chapter list.
   * `select_question_groups()` executes:
     * Queries database for root questions matching `subject_id = 1`, `document_type = 'RTP'`, and `chapter_id IN [101, 102, 103]`.
     * `build_group()` constructs `QuestionGroup` DTOs, parses shared context once via BeautifulSoup, and computes total marks without double counting.
     * Runs 100 randomized shuffle iterations to pick 5 questions meeting the constraints.
   * Preview API responds:
     `{ available_questions: 14, selected_question_count: 5, selected_total_marks: 72, selection_quality: "100%", root_question_ids: [41, 45, 48, 52, 57] }`.
4. **Activating Download**:
   * Frontend displays preview summary card (5 Questions Selected, 72 Marks, 100% Quality).
   * User clicks **Generate Paper** -> enables the download action buttons.

---

### Step 6: Generating & Downloading the Question Paper PDF

1. **User Action**: User clicks **Download Question Paper**.
2. **Request Dispatch**:
   * `paperService.downloadQuestionPaper()` posts `{ paper_title: "CA Final FR Mock Test - Series 1", root_question_ids: [41, 45, 48, 52, 57] }` to `/api/v1/generate/question-paper/`.
3. **Backend Rendering Engine** (`pdf_renderer.py`):
   * `_validate_root_question_ids` confirms all 5 IDs are root questions belonging to Financial Reporting RTPs.
   * `fetch_groups_by_ids([41, 45, 48, 52, 57])` fetches DTOs in the exact requested order.
   * `_render_question_paper_html()`:
     * Generates A4 header metadata block: Title, Subject, Level, Module, Date.
     * Renders "Question 1.", "Question 2.", ..., "Question 5." sequentially.
     * Deduplicates shared context case study blocks across sub-questions.
     * Injects right-aligned marks tags (`[16 Marks]`, `[4 Marks]`).
     * Injects table image crops and formula visual containers.
   * `_html_to_pdf()`:
     * Resolves `/media/table_crops/...` to absolute server file paths.
     * Substitutes rupee glyphs (`₹` -> `Rs.`).
     * `xhtml2pdf` compiles HTML to raw binary PDF bytes in memory (`io.BytesIO`).
4. **Streaming Response**:
   * Returns `HttpResponse(pdf_bytes, content_type='application/pdf')` with header `Content-Disposition: attachment; filename="CA_Final_FR_Mock_Test_-_Series_1.pdf"`.
5. **Browser Download**:
   * Axios receives blob -> creates `window.URL.createObjectURL(blob)` -> triggers synthetic download anchor -> browser saves `CA_Final_FR_Mock_Test_-_Series_1.pdf`.

---

### Step 7: Generating & Downloading the Synchronized Answer Sheet PDF

1. **User Action**: User clicks **Download Suggested Answers**.
2. **Request Dispatch**:
   * `paperService.downloadAnswerSheet()` sends `POST /api/v1/generate/answer-sheet/` with the **exact same `root_question_ids: [41, 45, 48, 52, 57]`**.
3. **Backend Rendering Engine** (`pdf_renderer.py`):
   * `fetch_groups_by_ids([41, 45, 48, 52, 57])` retrieves the exact same question groups.
   * `_render_answer_sheet_html()`:
     * Generates Suggested Answers header block.
     * Loops through groups 1 to 5 with identical sequential numbering ("Question 1.", "Question 2.", ...).
     * Renders root solutions, sub-question answers (`(a)`, `(b)`), and calculation ledgers.
     * Embeds structured working notes containers (`<div class="working-notes">`).
     * Omits repetitive question case study text to keep answer keys clean.
   * `xhtml2pdf` compiles HTML into memory PDF bytes.
4. **Delivery**:
   * Response returns with filename `"CA_Final_FR_Mock_Test_-_Series_1_Answer_Sheet.pdf"`.
   * Browser triggers download.

---

## Data Transformation Pipeline Across the Workflow

```
[ Raw PDF Document: 38 Pages on Disk ]
       |
       |  PyMuPDF (fitz) text & drawing extraction + visual cropping
       v
[ Raw Tokens + Clean Text + Image Crops in /media/ ]
       |
       |  DocumentLayoutDetector + SectionSplitter (q_part / a_part)
       v
[ Sliced Text Segments + Base Offset Trackers ]
       |
       |  QuestionParser + AnswerParser + HeaderValidator
       v
[ ParsedQuestion & ParsedAnswer DTOs with Canonical Hierarchy Paths ]
       |
       |  AnswerMatcher (1:1 Key Matching) + ChapterMapper + MarksExtractor
       v
[ Enriched Question Records Persisted in SQLite (`papers_question`) ]
       |
       |  QuestionSelector.build_group() (BeautifulSoup DOM parsing)
       v
[ QuestionGroup DTOs (Clean Question HTML, Answer HTML, SubQuestions, Canonical Marks) ]
       |
       |  Randomized Best-Fit Selection Algorithm (100 iterations)
       v
[ Ordered `root_question_ids` cached in React Client State ]
       |
       +---------------------------------------+
       |                                       |
       | pdf_renderer.py (Question Paper)      | pdf_renderer.py (Suggested Answers)
       v                                       v
[ Print-Ready Question Paper HTML ]    [ Print-Ready Suggested Answers HTML ]
       |                                       |
       | xhtml2pdf (In-Memory pisa compile)    | xhtml2pdf (In-Memory pisa compile)
       v                                       v
[ Raw Question Paper PDF Bytes ]       [ Raw Answer Sheet PDF Bytes ]
       |                                       |
       | HTTP Stream (Content-Disposition)     | HTTP Stream (Content-Disposition)
       v                                       v
[ "Practice_Paper.pdf" on Client Device ] [ "Practice_Paper_Answer_Sheet.pdf" on Client Device ]
```

---

## Conclusion & Architectural Summary

1. **Stateless Generation**: Practice papers and answer sheets are assembled and compiled on demand directly from atomic question records, avoiding static pre-generation storage overhead.
2. **Guaranteed Consistency**: By anchoring both question paper and answer sheet generation to the same cached `root_question_ids` array, solutions are 100% synchronized with questions.
3. **Resilient Document Extraction**: By combining PyMuPDF visual cropping with regex-driven hierarchy parsing and rule-based chapter mapping, the system handles complex, multi-column CA examination layouts with high fidelity.
