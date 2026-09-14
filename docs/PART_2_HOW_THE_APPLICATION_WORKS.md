# Part 2: How the Application Actually Works

This document provides a comprehensive, code-verified technical breakdown of the actual implemented workflows in the **TestSeries** application. Every step is traced from the user's browser action through the React components, HTTP/REST API layer, Django REST Framework views, backend services, extraction pipelines, database models, and PDF rendering engines.

---

## 1. Subject & Chapter Management

### 1.1 Overview & Architecture
Subject and chapter management handles the organizational hierarchy of the syllabus.
* **Relevant Files**:
  * Frontend: `frontend/src/pages/Subjects.jsx`, `frontend/src/services/subjectService.js`
  * Backend Models: `backend/apps/syllabus/models.py` (`Subject`, `Chapter`, `ChapterKeyword`)
  * Backend Serializers: `backend/apps/syllabus/serializers.py` (`SubjectSerializer`, `ChapterSerializer`)
  * Backend Views: `backend/apps/syllabus/views.py` (`SubjectViewSet`, `ChapterViewSet`)
  * Backend URLs: `backend/apps/syllabus/urls.py`

---

### 1.2 Loading & Filtering Subjects
```
User clicks 'Subjects' tab
  -> React mounts frontend/src/pages/Subjects.jsx
  -> useEffect triggers fetchSubjects()
  -> calls subjectService.getSubjects(selectedLevel)
  -> HTTP GET /api/v1/subjects/?exam_level=Final
  -> Django URL router routes to SubjectViewSet.as_view({'get': 'list'})
  -> SubjectViewSet.get_queryset()
       * Filters Subject.objects.filter(is_active=True)
       * Annotates chapters_count=Count('chapters')
       * Applies optional exam_level query filter
       * Orders alphabetically by name
  -> SubjectSerializer serializes queryset
  -> HTTP 200 OK JSON response with array of subject objects
  -> React sets subjects state & renders subject cards showing name, exam_level badge, and chapters_count
```

---

### 1.3 Creating a Subject
```
User opens "Add Subject" modal -> enters Name (e.g., "Financial Reporting") & Exam Level ("Final") -> clicks Save
  -> Frontend validates non-blank name and exam_level
  -> calls subjectService.createSubject({ name, exam_level })
  -> HTTP POST /api/v1/subjects/
  -> SubjectViewSet.as_view({'post': 'create'})
  -> SubjectSerializer.validate(attrs)
       * Normalizes whitespace (collapses consecutive spaces)
       * Performs case-insensitive duplicate check: Subject.objects.filter(name__iexact=name, exam_level=exam_level)
       * Raises serializers.ValidationError if duplicate exists for the same exam level
  -> Subject.save()
       * Executes normalize_syllabus_name() which applies Title Case while strictly preserving standard accounting acronyms defined in ACRONYM_MAP (e.g., "Ind", "AS", "GST", "TDS", "CARO", "AFM", "FR")
       * Calls Subject.clean() for final model-level validation
       * Inserts record into database table syllabus_subject
  -> HTTP 201 Created response
  -> Frontend closes modal, refreshes subjects list via fetchSubjects()
```

---

### 1.4 Editing a Subject
```
User clicks "Edit" on a subject card -> modifies name or exam level -> clicks Save
  -> calls subjectService.updateSubject(subjectId, { name, exam_level })
  -> HTTP PATCH /api/v1/subjects/<subject_id>/
  -> SubjectViewSet.as_view({'patch': 'partial_update'})
  -> SubjectSerializer.validate() excludes current subject ID from duplicate check
  -> Subject.save() normalizes and updates record in DB
  -> HTTP 200 OK
  -> Frontend updates local state and re-fetches list
```

---

### 1.5 Deleting a Subject (Cascade Safety & Impact Preview)
```
User clicks "Delete" on a subject card
  -> Frontend calls subjectService.getSubjectStats(subjectId)
  -> HTTP GET /api/v1/subjects/<subject_id>/stats/
  -> SubjectViewSet.stats() returns:
       {
         "chapters_count": subject.chapters.count(),
         "documents_count": subject.documents.count(),
         "questions_count": Question.objects.filter(document__subject=subject).count()
       }
  -> Frontend displays modal with impact warning (e.g., "Deleting this subject will permanently remove 12 chapters, 4 uploaded documents, and 68 extracted questions.")
  -> User confirms deletion
  -> calls subjectService.deleteSubject(subjectId)
  -> HTTP DELETE /api/v1/subjects/<subject_id>/
  -> SubjectViewSet.destroy() runs inside an atomic transaction (with transaction.atomic()):
       1. subject.generated_papers.all().delete()
       2. subject.documents.all().delete() (cascades to ExtractionLogs and Questions in SQLite)
       3. subject.chapters.all().delete()
       4. subject.delete()
  -> HTTP 204 No Content
  -> Frontend removes subject from UI state
```

---

### 1.6 Managing Chapters
```
User clicks "Manage Chapters" on a subject card
  -> Frontend calls subjectService.getSubjectChapters(subjectId)
  -> HTTP GET /api/v1/subjects/<subject_id>/chapters/
  -> ChapterViewSet.get_queryset() filters by subject_id, orders by F('chapter_order').asc(nulls_last=True)
  -> ChapterSerializer returns ordered array of chapter objects

Adding a Chapter:
  -> User enters chapter name (e.g., "Ind AS 115 - Revenue from Contracts with Customers") -> clicks Add
  -> calls subjectService.createChapter(subjectId, { chapter_name })
  -> HTTP POST /api/v1/subjects/<subject_id>/chapters/
  -> ChapterViewSet.perform_create():
       * Queries max_order = Chapter.objects.filter(subject=subject).aggregate(Max('chapter_order'))
       * Computes next_order = (max_order or 0) + 1
       * Chapter.save() normalizes name via normalize_syllabus_name()
       * Inserts record with contiguous chapter_order
  -> HTTP 201 Created -> Frontend updates chapter list and subject card badge count

Reordering a Chapter:
  -> User clicks Up or Down arrow on a chapter
  -> calls subjectService.reorderChapter(chapterId, 'up' | 'down')
  -> HTTP POST /api/v1/chapters/<chapter_id>/reorder/ with { direction: 'up' }
  -> ChapterViewSet.reorder():
       * Fetches all sibling chapters for the subject ordered by chapter_order
       * Checks for gaps/duplicates (safe-healing logic)
       * Swaps chapter_order values of adjacent chapters
       * Executes Chapter.objects.bulk_update(to_update, ['chapter_order']) inside transaction.atomic()
  -> HTTP 200 OK -> Frontend re-renders ordered list

Deleting a Chapter:
  -> User clicks Delete on a chapter
  -> HTTP DELETE /api/v1/chapters/<chapter_id>/
  -> ChapterViewSet.destroy():
       * Integrity Guard: checks if chapter.questions.count() > 0
       * If extracted questions reference this chapter: returns HTTP 400 Bad Request ("Cannot delete chapter because N extracted questions reference it.")
       * If zero questions reference it: inside transaction.atomic(), deletes chapter and re-indexes remaining sibling chapters to maintain a contiguous 1..N order sequence via bulk_update
  -> HTTP 204 No Content
```

---

## 2. Upload Paper Workflow

### 2.1 Overview & Architecture
The upload workflow receives ICAI past examination papers, revision test papers (RTP), or mock test papers (MOCK) in PDF format, performs validation, stores the file securely, creates tracking records, and queues background processing.
* **Relevant Files**:
  * Frontend: `frontend/src/pages/Upload.jsx`, `frontend/src/services/documentService.js`, `frontend/src/constants/documentConstants.js`
  * Backend Models: `backend/apps/documents/models.py` (`Document`)
  * Backend Serializers: `backend/apps/documents/serializers.py` (`DocumentUploadSerializer`)
  * Backend Views: `backend/apps/documents/views.py` (`DocumentUploadView`)
  * Background Task: `backend/apps/extraction/tasks.py` (`extract_document_task`)

---

### 2.2 Upload Step-by-Step Flow

```
1. User navigates to /upload
   - Upload.jsx mounts.
   - useEffect invokes subjectService.getSubjects() to populate the subject dropdown with active subjects.

2. User selects / drops PDF file
   - handleFile(file) checks:
     * MIME type is 'application/pdf' or extension is '.pdf'
     * Size <= 100 MB (100 * 1024 * 1024 bytes)
   - Smart Auto-Detection:
     * Regex scans filename for month keywords (e.g. "may", "nov", "jan") -> auto-sets exam_month
     * Regex scans filename for 4-digit years (e.g. "2024", "2025") -> auto-sets paper_year

3. User completes required fields:
   - Subject: Dropdown selection (e.g. "Financial Reporting")
   - Document Type: Choice of 'RTP', 'PYQ', 'MOCK'
   - Paper Year: Number input (e.g. 2026)
   - Exam Month: Choice of 'January', 'May', 'September', 'November', etc.
   - Title: Optional (if left empty, backend auto-generates canonical title)

4. User clicks "Upload Paper"
   - Frontend creates a FormData object:
     formData.append('subject', Number(subjectId))
     formData.append('document_type', document_type)
     formData.append('paper_year', Number(paper_year))
     formData.append('exam_month', exam_month)
     formData.append('title', title.trim())
     formData.append('file', fileObject)
   - Axios posts to /api/v1/documents/upload/ with multipart/form-data and tracks upload percentage via onUploadProgress.

5. Backend Validation (DocumentUploadSerializer):
   - validate_file(): Verifies .pdf extension, application/pdf MIME type, and MAX_UPLOAD_SIZE limit.
   - validate_paper_year(): Enforces 1900 <= paper_year <= (current_year + 1).
   - validate():
     * If title is empty, generates canonical title: "{subject.name} - {document_type} - {exam_month} {paper_year}"
     * If custom title is provided, smart-aligns exam_month if title contains month keyword.
     * Enforces case-insensitive title uniqueness across all Document records.

6. Storage & Task Dispatch (DocumentUploadView):
   - perform_create() saves physical file to disk using Django default_storage:
     file_path = default_storage.save(f'documents/{file_obj.name}', file_obj)
     (Files are written to backend/media/documents/<filename>.pdf)
   - Resolves or creates default system user.
   - Creates Document ORM instance with:
     * storage_path = file_path
     * extraction_status = "PENDING"
   - Asynchronously queues Celery extraction task:
     extract_document_task.delay(instance.document_id)
   - If Celery broker is unavailable, catches exception and logs failure in ExtractionLog.

7. Response & Frontend Polling Transition:
   - HTTP 201 Created returned:
     {
       "document_id": 14,
       "title": "Financial Reporting - RTP - May 2026",
       "subject": { "subject_id": 2, "name": "Financial Reporting", "exam_level": "Final" },
       "status": "PENDING",
       "uploaded_at": "2026-09-14T10:30:00Z"
     }
   - Frontend receives document_id and navigates to /processing/14.
   - Processing.jsx polls GET /api/v1/documents/14/ and GET /api/v1/extraction-logs/?document_id=14 every 2 seconds.
   - When status transitions to 'COMPLETED', Processing.jsx waits 1.5s and automatically redirects to /review/14.
```

---

## 3. PDF Extraction Pipeline

### 3.1 Overview & Architecture
The extraction pipeline is an industrial-grade document processing engine designed for complex ICAI examination papers containing multi-column layouts, interleaved suggested answers, mathematical equations, financial statements, and case studies.

* **Pipeline Entry Point**: `backend/apps/extraction/services/extraction_service.py` -> `ExtractionService.trigger_extraction()`
* **Core Pipeline Engine**: `backend/apps/extraction/services/extraction_pipeline.py` -> `extract_document()`
* **Key Subservices**:
  1. `pdf_loader.py`: Safe PyMuPDF document loader
  2. `text_extractor.py`: Coordinate-aware text & margin extraction
  3. `table_processing.py`: Table boundary grouping, visual raster cropping & markdown rendering
  4. `normalizer.py`: OCR character & glyph normalization
  5. `layout_detector.py`: Section-wise vs Interleaved layout classification
  6. `section_splitter.py`: Character-accurate document section slicing
  7. `question_parser.py` & `header_validator.py`: Greedy regex & hierarchy parsing
  8. `answer_parser.py`: Answer section & Working Notes parser
  9. `answer_matcher.py`: Canonical hierarchy path 1:1 matcher
  10. `marks_extractor.py`: Tiered marks extraction
  11. `question_classifier.py`: Question type classifier (MCQ, PRACTICAL, THEORY, DESCRIPTIVE)
  12. `instruction_detector.py`: Choice/compulsory instruction detector
  13. `chapter_mapper.py`: Syllabus chapter keyword matcher
  14. `html_formatter.py`: HTML structure builder & table cleaner

---

### 3.2 Pipeline Data Structures (DTOs)
The pipeline passes typed dataclasses between stages to avoid mutable state bugs:

```python
# Defined in backend/apps/extraction/services/types.py

@dataclass
class ParsedQuestion:
    hierarchy_path: List[str]       # e.g., ["1", "a", "i"]
    raw_header: str                 # e.g., "Question 1(a)(i)"
    text: str                       # Plain question text
    start_offset: int               # Character offset in raw document
    end_offset: int
    start_page: int                 # 1-indexed source PDF page
    end_page: int
    level: QuestionLevel            # MAIN, SUB, SUB_SUB
    shared_context: Optional[str]   # Preceding case study text

@dataclass
class WorkingNote:
    number: str                     # e.g., "1", "2"
    title: Optional[str]            # e.g., "Calculation of Purchase Consideration"
    content: str                    # Body text/tables of working note

@dataclass
class ParsedAnswer:
    hierarchy_path: List[str]       # e.g., ["1", "a", "i"]
    raw_header: str                 # e.g., "Answer to Q.1(a)(i)"
    text: str                       # Answer body text
    start_offset: int
    end_offset: int
    start_page: int
    end_page: int
    working_notes: List[WorkingNote]# Isolated working notes list
```

---

### 3.3 Stage-by-Stage Extraction Flow

```
====================================================================================================
STAGE 1: ISOLATION & PDF LOADING (extraction_service.py -> extraction_pipeline.py)
====================================================================================================
- ExtractionService copies uploaded PDF to a unique sandbox directory: backend/temp/<doc_id>_<uuid>.pdf
- Creates ExtractionLog record with status 'PROCESSING'
- Updates Document.extraction_status = 'PROCESSING'
- Calls extract_document(document, temp_file_path)
- PyMuPDF opens PDF via load_pdf(pdf_path) -> returns fitz.Document instance

====================================================================================================
STAGE 2: MARGIN FILTERING & VISUAL CROPPING (text_extractor.py & table_processing.py)
====================================================================================================
1. Margin Header/Footer Detection:
   - detect_headers_footers() scans top 135pt and bottom 135pt margins across all pages.
   - Text repeated across >= 30% of pages (e.g., "REVISION TEST PAPERS - MAY 2026", page numbers)
     is added to repeated_margin_texts set and stripped from extracted body text.

2. Table Detection & Visual Cropping (Pass 1 - TableProcessor.process_document):
   - page.find_tables() detects all tabular grid boundaries.
   - Nearby tables on the same page (vertical gap <= 60pt) without intervening question headers
     are grouped into unified visual regions.
   - If the table is an MCQ Answer Key table (is_mcq_answer_key_table), it is serialized to text.
   - If the table is a Complex Financial Table (Balance Sheet, Profit & Loss, Ledger):
     * PyMuPDF renders a high-res raster crop: page.get_pixmap(matrix=200/72, clip=crop_rect)
     * Saves PNG image to backend/media/table_crops/doc<id>_p<page>_y<y>.png
     * Generates HTML visual container:
       <div class="table-container" data-is-complex="true" data-crop-path="/media/table_crops/doc14_p3_y120.png">
         <img src="/media/table_crops/doc14_p3_y120.png" />
       </div>

3. Mathematical Formula Detection (find_standalone_equation_regions):
   - Inspects vector drawings (page.get_drawings()) for horizontal fraction lines (width 15-250pt, height <= 2.5pt).
   - Scans text spans for multi-line Greek symbol stacks (σ, β, μ, ρ, Cov, ∑, √).
   - Crops formula regions to backend/media/formula_crops/doc<id>_p<page>_formula_y<y>.png.

4. Page Text Reconstruction (Pass 2):
   - Text blocks outside tables/formulas are normalized (PUA math glyphs converted to standard Unicode, backticks ` replaced with ₹).
   - Combines text, table blocks, and formula blocks in vertical reading order (y0, then x0), wrapping non-text blocks in [STRUCTURED_START]...[STRUCTURED_END] markers.
   - Produces full_text string and a list of page_offsets: [(0, page_1), (offset_2, page_2), ...].

====================================================================================================
STAGE 3: NORMALIZATION & LAYOUT DETECTION (layout_detector.py & section_splitter.py)
====================================================================================================
1. Normalizer.pre_normalize_ocr(full_text):
   - Normalizes OCR spacing errors, collapses multiple spaces, fixes common ligature splits.
2. DocumentLayoutDetector:
   - Evaluates full_text against section delimiter patterns (e.g., "PART II - QUESTIONS AND ANSWERS", "SUGGESTED ANSWERS", "DIVISION B - DESCRIPTIVE QUESTIONS").
   - Identifies whether layout is SECTION_WISE (all questions in first half, all answers in second half) or INTERLEAVED (Question 1 followed immediately by Answer 1).
3. SectionSplitter:
   - If SECTION_WISE: splits full_text at boundary_position into q_part (questions text) and a_part (answers text), setting q_base_offset=0 and a_base_offset=boundary_position.
   - Detects question start boundary (skips cover/syllabus front matter).

====================================================================================================
STAGE 4: QUESTION PARSING (question_parser.py & header_validator.py)
====================================================================================================
1. Regex Matching:
   - Matches question header patterns (e.g., r"^Question\s+(?:No\.\s*)?(\d+)", r"^\((\w+)\)", r"^\b(\d{1,2})\.\s+").
   - Resolves overlapping matches based on length and pattern priority.
2. Validation (HeaderValidator):
   - Filters out false positives: dates ("May 2024"), monetary references ("Rs. 50,000"), statutory section references ("Section 115JB"), inline numbered lists.
3. Hierarchy Construction (HierarchyUtils):
   - Builds canonical hierarchy paths: Main question "1" -> Sub-question "(a)" -> Sub-sub-question "(i)" = ["1", "a", "i"].
   - Identifies preceding shared context (case study paragraphs before sub-question lists) and attaches it to ParsedQuestion.shared_context.
   - Uses binary search on page_offsets to assign exact start_page and end_page.

====================================================================================================
STAGE 5: ANSWER PARSING (answer_parser.py)
====================================================================================================
1. Header Detection:
   - Matches answer headers in a_part (e.g., r"^Answer\s+to\s+Question\s+(?:No\.\s*)?(\d+)", r"^Ans\.\s*(\d+)\s*\(([a-z]+)\)", r"^Solution\s*:").
2. Working Notes Extraction:
   - Detects Working Notes headings (e.g., "Working Notes:", "Working Note 1: Calculation of Goodwill").
   - Extracts WorkingNote DTOs with isolated title and content.
3. Output: List of ParsedAnswer objects with canonical hierarchy paths.

====================================================================================================
STAGE 6: CANONICAL MATCHING (answer_matcher.py)
====================================================================================================
- AnswerMatcher maps questions and answers by hierarchy path tuple (e.g., ('1', 'a')).
- Matches exactly 1:1 question-to-answer pairs.
- Prevents self-matching on identical character offsets.
- Records unmatched questions, unmatched answers, and duplicates into MatchingDiagnostics.

====================================================================================================
STAGE 7: ENRICHMENT HOOKS (marks, classification, chapter mapping, html formatting)
====================================================================================================
1. Chapter Mapping (chapter_mapper.py):
   - Pre-loads all chapters of the subject (get_prepared_chapters).
   - find_chapter_for_question_context inspects the 400 characters of text immediately preceding the question start.
   - Compares text against chapter keywords, Ind AS numbers, and syllabus patterns with weighted scoring (exact name=5, topic=2, code=1).
   - Assigns matched Chapter foreign key.

2. Marks Extraction (marks_extractor.py):
   - Tiered regex search: "16 Marks", "[16 Marks]", "(4 x 4 = 16 Marks)", "(5)".
   - Enforces exclusion patterns (excluding Section numbers, Year dates, Table row numbers).

3. Question Classification (question_classifier.py):
   - Classifies question into MCQ, PRACTICAL, or THEORY:
     * MCQ: Detects options (a), (b), (c), (d) or MCQ answer key pattern.
     * PRACTICAL: Matches computational imperatives ("Calculate", "Compute", "Prepare Balance Sheet", "Journal Entries", "Total Income and Tax Liability").
     * THEORY: Matches conceptual imperatives ("Explain", "Discuss", "State the provisions", "Examine whether", "Advise").

4. HTML Formatting (html_formatter.py):
   - clean_metadata_text(): Strips running exam header lines from text.
   - format_question_content(): Converts text to semantic HTML, wrapping shared context in <div class="shared-context">.
   - format_answer_content(): Formats answer text and appends <div class="working-notes"> containing structured working notes.

====================================================================================================
STAGE 8: DATABASE PERSISTENCE & CLEANUP
====================================================================================================
- Inside transaction.atomic():
  1. Question.objects.filter(document=document).delete() (clears previous partial attempts)
  2. Updates Document.total_pages
  3. Consolidates sub-questions under primary question root keys ("1", "2", "1.1")
  4. Inserts Question records into SQLite
  5. Updates Document.extraction_status = 'COMPLETED'
  6. Updates ExtractionLog.status = 'COMPLETED' with execution duration, match counts, and rejection summary
- ExtractionService finally block removes temporary sandbox PDF.
```

---

## 4. Review Workflow

### 4.1 Overview & Architecture
The Review page is the human-in-the-loop verification interface where educators and administrators verify extracted questions, correct OCR mistakes, adjust marks, reclassify question types, and map or create chapters.

* **Relevant Files**:
  * Frontend: `frontend/src/pages/Review.jsx`, `frontend/src/services/questionService.js`, `frontend/src/services/subjectService.js`, `frontend/src/services/documentService.js`
  * Backend Model: `backend/apps/papers/models.py` (`Question`)
  * Backend Serializer: `backend/apps/papers/serializers.py` (`QuestionSerializer`)
  * Backend View: `backend/apps/papers/views.py` (`QuestionDetailView`, `QuestionListView`)

---

### 4.2 Review Flow & Data Operations

```
1. Loading Review Data:
   - Review.jsx calls:
     * documentService.getDocument(documentId) -> GET /api/v1/documents/:id/
     * questionService.getQuestions(documentId) -> GET /api/v1/questions/?document_id=:id
     * documentService.getExtractionLogs(documentId) -> GET /api/v1/extraction-logs/?document_id=:id
     * subjectService.getSubjectChapters(subjectId) -> GET /api/v1/subjects/:subject_id/chapters/
   - Renders Statistics Bar: Total Questions, With Answers, Missing Answers, Extraction Duration, Matches Count.

2. Filtering & Sorting:
   - Search Query: Real-time filtering across question text, question number, answer text, and chapter name.
   - Status Filter: 'ALL', 'ANSWERED', 'MISSING'.
   - Marks Filter: Dynamic dropdown populated from unique marks extracted.
   - Sort By: Question Number (Asc/Desc) or Marks (Asc/Desc).

3. Displaying Rendered Content:
   - Question & Answer text are rendered as formatted HTML.
   - High-resolution table/formula PNG crops are displayed via /media/table_crops/... and /media/formula_crops/... with zoomable click-to-preview capability.
   - Shared case study contexts are highlighted in dedicated alert containers.
   - Working notes are rendered in structured note boxes.

4. Editing a Question:
   - User clicks "Edit" on a Question Card.
   - Form initializes with: question_number, question_text, answer_text, chapter, question_type.
   - User can edit content directly in textareas.

5. Chapter Selection & Inline Chapter Creation:
   - Existing Chapter Selection: User selects from the SearchableSelect dropdown of subject chapters.
   - Inline Creation: If a user types a chapter name that does not exist:
     * UI prompts "Create chapter '<name>'?"
     * User confirms -> Frontend calls subjectService.createChapter(subjectId, { chapter_name: name })
     * Calls POST /api/v1/subjects/<subject_id>/chapters/ -> backend creates Chapter record
     * Frontend receives new chapter object, appends it to chapters state, and auto-selects it in editForm.

6. Submitting Edits:
   - User clicks "Save Changes" -> Frontend validates non-blank fields.
   - Calls questionService.updateQuestion(questionId, payload)
   - HTTP PATCH /api/v1/questions/<question_id>/
   - QuestionSerializer.validate():
     * Enforces chapter belongs to the subject of the question's document:
       if chapter.subject_id != document.subject_id: raise ValidationError(...)
   - QuestionSerializer.update():
     * Trims whitespace.
     * Auto-converts updated plain text into semantic HTML using text_to_html():
       validated_data['question_content'] = text_to_html(validated_data['question_text'])
       validated_data['answer_content'] = text_to_html(validated_data['answer_text'])
     * Saves updated fields to database.
   - HTTP 200 OK returned with updated Question object.
   - Frontend updates the local questions state array in-place (no full-page reload).

7. Navigation Safety Guards:
   - isFormDirty memo checks if any form field differs from the database state.
   - React Router v7 useBlocker intercepts internal SPA route transitions and displays a confirmation dialog.
   - window.onbeforeunload intercepts browser tab closure or page refresh.
```

---

## 5. Generate / Preview Workflow

### 5.1 Overview & Architecture
The Generate page provides an interactive practice paper configuration studio. Users filter by syllabus module, marks, question counts, chapters, and exam sessions. The selection engine uses a randomized best-fit algorithm to pick questions matching the exact criteria.

* **Relevant Files**:
  * Frontend: `frontend/src/pages/Generate.jsx`, `frontend/src/services/paperService.js`
  * Backend Serializers: `backend/apps/papers/serializers.py` (`GenerationFilterSerializer`)
  * Backend Views: `backend/apps/papers/views.py` (`GeneratePreviewView`)
  * Selection Service: `backend/apps/papers/services/question_selector.py` (`select_question_groups`, `build_group`)

---

### 5.2 Filter State & Module Rules

The frontend and backend enforce module-dependent constraint rules:

| Module | Purpose | Required Constraint | Chapter Filtering | Default Value |
| :--- | :--- | :--- | :--- | :--- |
| **RTP** | Revision Test Paper | `question_count` (Count-based) | Enabled (Multi-select chapters) | 5 questions |
| **PYQ** | Previous Year Questions | `total_marks` (Marks-based) | Disabled | 50 marks |
| **MOCK** | Full Mock Exam | `total_marks` (Marks-based) | Disabled | 50 marks |

Optional filters available on all modules: `question_type` (THEORY, PRACTICAL, MCQ, DESCRIPTIVE, MIXED), `year_from`, `year_to`, `exam_month`.

---

### 5.3 Step-by-Step Preview Flow

```
1. User configures filters on /generate
   - Selects Subject (e.g. "Financial Reporting")
   - Selects Module ('RTP', 'PYQ', or 'MOCK')
   - Sets target Total Marks (for PYQ/MOCK) or Question Count (for RTP)
   - (Optional) Selects specific chapters, question types, or year range.

2. Debounced Preview Trigger:
   - A 600ms debounce timer (DEBOUNCE_MS = 600) fires when filter inputs change.
   - Calls paperService.generatePreview(filters)
   - HTTP POST /api/v1/generate/preview/

3. Backend Validation (GenerationFilterSerializer):
   - Validates module is 'RTP', 'PYQ', or 'MOCK'.
   - Enforces chapter_ids is only accepted when module == 'RTP'.
   - Sets default total_marks = 50 if PYQ/MOCK total_marks is omitted.
   - Sets default question_count = 5 if RTP question_count is omitted.
   - Validates year_from <= year_to.

4. Selection Engine (question_selector.py -> select_question_groups):
   - Database Query:
     Question.objects.filter(
         parent_question__isnull=True,
         document__subject_id=filters['subject_id'],
         document__document_type=filters['module']
     ).select_related('document__subject', 'chapter')
      .prefetch_related(Prefetch('sub_questions', queryset=Question.objects.order_by('hierarchy_key')))
   - Applies optional filters: chapter_ids, question_type, paper_year ranges, exam_month.
   - DTO Assembly & HTML Parsing (build_group):
     * Parses stored HTML once using BeautifulSoup.
     * Isolates and extracts <div class="shared-context"> into group.shared_context_html.
     * Computes Canonical Marks Rule (avoids double counting):
       If root question has child sub-questions with marks, total_marks = sum(child_marks).
       Otherwise, total_marks = root.marks.
     * Assembles QuestionGroup DTO.
   - Randomized Best-Fit Selection:
     * Runs SELECTION_ATTEMPTS = 100 iterations.
     * Each iteration shuffles the eligible groups (random.shuffle(all_groups)).
     * Performs a greedy pass: adds questions until marks target or question count is reached without exceeding.
     * Tracks the combination closest to the target.
     * Short-circuits immediately upon a 100% perfect fit.

5. Preview Response:
   - GeneratePreviewView returns:
     {
       "available_questions": 42,
       "available_marks": 210,
       "selected_question_count": 5,
       "selected_total_marks": 50,
       "selection_quality": "100%",
       "root_question_ids": [142, 89, 214, 105, 178],
       "warning": null
     }

6. Frontend State Update:
   - Generate.jsx stores root_question_ids in React state.
   - Displays summary stats (Selected Marks, Question Count, Available Pool).
   - User clicks "Generate Paper" -> activates forceEnabled=true -> enables download buttons.
```

---

## 6. Question Paper Generation

### 6.1 Overview & Architecture
Produces a professional, print-ready A4 Question Paper PDF matching ICAI examination formatting. The process is completely stateless—PDFs are generated in memory and streamed directly to the browser without database writes or temp file leftovers.

* **Relevant Files**:
  * Frontend: `frontend/src/pages/Generate.jsx`, `frontend/src/services/paperService.js`
  * Backend Serializer: `backend/apps/papers/serializers.py` (`PDFGenerationSerializer`)
  * Backend View: `backend/apps/papers/views.py` (`GenerateQuestionPaperView`)
  * Rendering Services: `backend/apps/papers/services/pdf_renderer.py`, `backend/apps/papers/services/question_selector.py` (`fetch_groups_by_ids`), `backend/apps/papers/services/filename_utils.py`

---

### 6.2 Step-by-Step Question Paper Download Flow

```
1. User clicks "Download Question Paper"
   - Frontend calls paperService.downloadQuestionPaper({
       paper_title: "CA Final FR Practice Paper",
       root_question_ids: [142, 89, 214, 105, 178],
       show_source: false,
       show_chapter: false
     })
   - HTTP POST /api/v1/generate/question-paper/ with responseType: 'blob'.

2. Backend Validation (PDFGenerationSerializer & _validate_root_question_ids):
   - PDFGenerationSerializer validates paper_title and ensures root_question_ids contains no duplicates.
   - _validate_root_question_ids verifies:
     * All IDs exist in the database.
     * All IDs are root questions (parent_question is NULL).
     * All questions belong to the same Subject.
     * All questions belong to the same Module (document_type).

3. Deterministic Group Fetching (fetch_groups_by_ids):
   - Queries Question records matching root_question_ids with select_related and prefetch_related.
   - Builds QuestionGroup DTOs via build_group().
   - Preserves the exact array order of root_question_ids supplied in the request (zero re-selection, zero randomness).

4. HTML Assembly (_render_question_paper_html):
   - Injects A4 print CSS:
     @page { size: a4 portrait; margin: 1.5cm 1.5cm 1.8cm 1.5cm; }
     body { font-family: "Times New Roman", Times, serif; font-size: 11pt; }
   - Builds Title Block: Paper title, Subject, Exam Level, Module, Date.
   - Deduplicates Shared Contexts: Compares group.shared_context_html with the previous question's context. If consecutive sub-questions share the same case study, the block is rendered only once.
   - Question Renumbering: Renumbers root questions sequentially (Question 1., Question 2., ...).
   - Preserves sub-question labels ((a), (b), (i), (ii)) and displays right-aligned marks badges ([4 Marks], [16 Marks]).
   - Renders financial tables and formula visual regions.

5. In-Memory PDF Compilation (_html_to_pdf):
   - _resolve_img_path regex finds all <img src="..."> tags and converts relative /media/... paths to absolute server disk paths.
   - Replaces rupee symbols (₹, `) with "Rs. " to prevent font glyph rendering errors.
   - Calls pisa.CreatePDF(html_str, dest=buf) (pure-Python xhtml2pdf).
   - Returns binary PDF bytes from memory buffer (buf.getvalue()).

6. Streaming Response:
   - Sanitizes filename via sanitize_filename(paper_title) -> "CA_Final_FR_Practice_Paper.pdf".
   - Returns HttpResponse(pdf_bytes, content_type='application/pdf') with header:
     Content-Disposition: attachment; filename="CA_Final_FR_Practice_Paper.pdf"

7. Browser Download:
   - Axios receives binary blob.
   - _triggerDownload() creates window.URL.createObjectURL(blob).
   - Dynamically creates an <a download="..."> anchor, appends to DOM, triggers click(), and revokes the object URL.
```

---

## 7. Answer Sheet Generation & 1:1 Consistency Guarantee

### 7.1 Overview & Architecture
Produces the companion Suggested Answers PDF. The critical technical requirement is **guaranteed consistency**: every question in the answer sheet must correspond exactly in identity, order, numbering, and sub-part structure to the generated question paper.

* **Relevant Files**:
  * Frontend: `frontend/src/pages/Generate.jsx`, `frontend/src/services/paperService.js`
  * Backend View: `backend/apps/papers/views.py` (`GenerateAnswerSheetView`)
  * Rendering Service: `backend/apps/papers/services/pdf_renderer.py` (`render_answer_sheet`, `_render_answer_sheet_html`)

---

### 7.2 How Consistency is Mathematically & Structurally Guaranteed

```
                                  [ Generate Page State ]
                                  root_question_ids: [142, 89, 214]
                                            |
                    +-----------------------+-----------------------+
                    |                                               |
                    v                                               v
       POST /generate/question-paper/                  POST /generate/answer-sheet/
       { root_question_ids: [142, 89, 214] }          { root_question_ids: [142, 89, 214] }
                    |                                               |
                    v                                               v
        fetch_groups_by_ids([142, 89, 214])            fetch_groups_by_ids([142, 89, 214])
                    |                                               |
                    v                                               v
           Same QuestionGroup DTOs                        Same QuestionGroup DTOs
                    |                                               |
                    v                                               v
        render_question_paper()                        render_answer_sheet()
        - Question 1. (from ID 142)                    - Question 1. Answer (from ID 142)
          (a) Sub-part 1                                 (a) Sub-part 1 Solution
          (b) Sub-part 2                                 (b) Sub-part 2 Solution
        - Question 2. (from ID 89)                     - Question 2. Answer (from ID 89)
        - Question 3. (from ID 214)                    - Question 3. Answer (from ID 214)
```

1. **Shared Cached ID Sequence**: When the user configures filters, `GeneratePreviewView` performs randomized selection **once** and returns the ordered `root_question_ids` array. The React frontend caches this exact array in state.
2. **No Backend Re-Selection**: When the user clicks "Download Question Paper" and "Download Suggested Answers", both endpoints receive the **exact same `root_question_ids` array**.
3. **Deterministic DTO Fetching**: `fetch_groups_by_ids` does not run any random shuffling or greedy selection. It constructs a dictionary lookup `q_map` and maps IDs in caller-supplied order:
   `[q_map[qid] for qid in root_question_ids if qid in q_map]`
4. **Synchronized Layout & Sub-Question Mapping**:
   * `render_question_paper` loops `for i, group in enumerate(groups, start=1)` -> renders `Question {i}.`
   * `render_answer_sheet` loops `for i, group in enumerate(groups, start=1)` -> renders `Question {i}.`
   * Sub-questions use identical preserved labels (`sq.sub_question_label`, e.g. `(a)`, `(b)`).
   * Shared context is intentionally omitted from the answer sheet to eliminate clutter (students refer to the question paper for case studies), while working notes and calculation tables are fully expanded.
   * Filename: `sanitize_filename(paper_title, suffix='_Answer_Sheet')` -> `"CA_Final_FR_Practice_Paper_Answer_Sheet.pdf"`.

---

## 8. Data Model & Schema Relationships

### 8.1 Core Models Breakdown

#### `Subject` (`backend/apps/syllabus/models.py`)
* **Represents**: An academic course subject in the CA syllabus.
* **Fields**:
  * `subject_id` (`BigAutoField`, Primary Key)
  * `name` (`CharField(max_length=150)`): Normalized subject name.
  * `exam_level` (`CharField(choices=['Foundation', 'Intermediate', 'Final'])`)
  * `is_active` (`BooleanField(default=True)`)
  * `created_at`, `updated_at` (`DateTimeField`)
* **Constraints**: `UniqueConstraint(fields=['name', 'exam_level'])`
* **Custom Methods**: `save()` normalizes casing via `normalize_syllabus_name()`.

#### `Chapter` (`backend/apps/syllabus/models.py`)
* **Represents**: A specific chapter or topic belonging to a subject.
* **Fields**:
  * `chapter_id` (`BigAutoField`, Primary Key)
  * `subject` (`ForeignKey(Subject, on_delete=models.PROTECT, related_name="chapters")`)
  * `chapter_name` (`CharField(max_length=100)`)
  * `chapter_order` (`IntegerField`): Contiguous 1..N sequence position.
* **Constraints**: `UniqueConstraint(fields=['subject', 'chapter_name'])`

#### `ChapterKeyword` (`backend/apps/syllabus/models.py`)
* **Represents**: Deterministic keywords mapped to a chapter for automated extraction matching.
* **Fields**:
  * `chapter_keyword_id` (`BigAutoField`, Primary Key)
  * `chapter` (`OneToOneField(Chapter, on_delete=models.CASCADE, related_name="keyword_record")`)
  * `keywords` (`TextField`): One keyword per line.

#### `Document` (`backend/apps/documents/models.py`)
* **Represents**: An uploaded source PDF question paper.
* **Fields**:
  * `document_id` (`BigAutoField`, Primary Key)
  * `user` (`ForeignKey(User, on_delete=models.CASCADE, related_name="documents")`)
  * `subject` (`ForeignKey(Subject, on_delete=models.PROTECT, related_name="documents")`)
  * `title` (`CharField(max_length=255)`)
  * `document_type` (`CharField(choices=['RTP', 'PYQ', 'MOCK'])`)
  * `paper_year` (`PositiveIntegerField`)
  * `exam_month` (`CharField(choices=['January', 'February', ..., 'December'])`)
  * `storage_path` (`TextField`): Relative path in media directory (e.g. `documents/paper.pdf`).
  * `total_pages` (`PositiveIntegerField`)
  * `extraction_status` (`CharField(choices=['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'])`)
  * `uploaded_at` (`DateTimeField`)
* **Indexes**: `idx_document_subject`, `idx_document_type`.

#### `ExtractionLog` (`backend/apps/extraction/models.py`)
* **Represents**: Processing logs and error diagnostics for a document extraction run.
* **Fields**:
  * `log_id` (`BigAutoField`, Primary Key)
  * `document` (`ForeignKey(Document, on_delete=models.CASCADE, related_name="extraction_logs")`)
  * `status` (`CharField(choices=['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'])`)
  * `message` (`TextField`): Summary of duration, questions extracted, match counts, and rejection details.

#### `Question` (`backend/apps/papers/models.py`)
* **Represents**: An individual extracted question or sub-question.
* **Fields**:
  * `question_id` (`BigAutoField`, Primary Key)
  * `parent_question` (`ForeignKey('self', on_delete=models.CASCADE, null=True, related_name="sub_questions")`)
  * `document` (`ForeignKey(Document, on_delete=models.CASCADE, related_name="questions")`)
  * `chapter` (`ForeignKey(Chapter, on_delete=models.PROTECT, null=True, related_name="questions")`)
  * `question_number` (`CharField(max_length=20)`): Root key (e.g. "1", "2", "1.1").
  * `sub_question_label` (`CharField(max_length=50, null=True)`): Part label (e.g. "(a)", "(i)").
  * `hierarchy_key` (`CharField(max_length=512, db_index=True)`): Canonical key (e.g. "1.a.i").
  * `question_content` (`TextField`): Render-ready HTML with `<div class="shared-context">` and visual container tags.
  * `question_text` (`TextField`): Raw plain text.
  * `answer_content` (`TextField`): Render-ready HTML with `<div class="working-notes">`.
  * `answer_text` (`TextField`): Raw plain text.
  * `question_type` (`CharField(max_length=30, default="UNIDENTIFIED")`): 'THEORY', 'PRACTICAL', 'MCQ', 'DESCRIPTIVE'.
  * `instruction_type` (`CharField(max_length=30, null=True)`): 'COMPULSORY', 'OPTIONAL', etc.
  * `marks` (`PositiveIntegerField(null=True)`)
  * `source_page` (`PositiveIntegerField(null=True)`): Source PDF page number.
* **Constraints**: `UniqueConstraint(fields=['document', 'hierarchy_key'])`
* **Indexes**: `idx_question_document`, `idx_question_chapter`, `idx_question_parent`, `idx_question_type`.

---

### 8.2 Entity Relationship Diagram

```
+-------------------------------------------------------------+
|                           Subject                           |
|-------------------------------------------------------------|
| PK  subject_id                                              |
|     name ("Financial Reporting")                            |
|     exam_level ("Final")                                    |
|     is_active (True)                                        |
+-------------------------------------------------------------+
       |                                             |
       | 1:N (PROTECT)                               | 1:N (PROTECT)
       v                                             v
+-----------------------------+               +-------------------------------------+
|           Chapter           |               |              Document               |
|-----------------------------|               |-------------------------------------|
| PK  chapter_id              |               | PK  document_id                     |
| FK  subject_id              |               | FK  subject_id                      |
|     chapter_name            |               |     title                           |
|     chapter_order (1..N)    |               |     document_type (RTP/PYQ/MOCK)    |
+-----------------------------+               |     paper_year                      |
       |               |                      |     exam_month                      |
       | 1:1 (CASCADE) | 1:N (PROTECT, null)  |     storage_path                    |
       v               |                      |     extraction_status               |
+--------------------+ |                      +-------------------------------------+
|   ChapterKeyword   | |                                |                 |
|--------------------| |                                | 1:N (CASCADE)   | 1:N (CASCADE)
| PK  chapter_kw_id  | |                                v                 v
| FK  chapter_id     | |                      +-------------------+ +---------------+
|     keywords       | |                      |   ExtractionLog   | |               |
+--------------------+ |                      |-------------------| |               |
                       |                      | PK  log_id        | |               |
                       |                      | FK  document_id   | |               |
                       |                      |     status        | |               |
                       |                      |     message       | |               |
                       |                      +-------------------+ |               |
                       +------------------------------+             |               |
                                                      |             |               |
                                                      v             v               |
                                           +------------------------------------+   |
                                           |              Question              |<--+
                                           |------------------------------------|
                                           | PK  question_id                    |
                                           | FK  document_id                    |
                                           | FK  chapter_id (nullable)          |
                                           | FK  parent_question_id (nullable)  |---+
                                           |     question_number ("1")          |   | 1:N (Self-referencing
                                           |     sub_question_label ("a")       |   | sub-questions)
                                           |     hierarchy_key ("1.a")          |<--+
                                           |     question_content (HTML)        |
                                           |     question_text (Plain)          |
                                           |     answer_content (HTML)          |
                                           |     answer_text (Plain)            |
                                           |     question_type                  |
                                           |     marks                          |
                                           |     source_page                    |
                                           +------------------------------------+
```
