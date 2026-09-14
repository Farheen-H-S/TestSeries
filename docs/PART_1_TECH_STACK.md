# Part 1: Tech Stack & Architecture Deep Dive

This document provides a thorough, code-verified technical breakdown of every technology, framework, and library actively used in the **TestSeries** application. All explanations reflect the actual implementation in the codebase.

---

## 1. Core Technologies vs Supporting Libraries vs Development Tools

```
+---------------------------------------------------------------------------------------------------+
|                                        APPLICATION ECOSYSTEM                                      |
+--------------------------------------------------+------------------------------------------------+
| CORE TECHNOLOGIES                                | SUPPORTING LIBRARIES                           |
| - React 19 (Frontend UI & State)                 | - Celery 5.4 (Asynchronous Task Queue)         |
| - React Router v7 (Client Routing & Blockers)   | - Redis 5.0 (Celery Message Broker)            |
| - Axios 1.18 (HTTP Client)                       | - Pillow 11.0 & OpenCV (Image processing)      |
| - Vanilla CSS & Design Tokens (Styling)          | - React Icons 5.7 (Iconography)                |
| - Django 4.2 / 5.2 (Backend Framework & ORM)     | - python-dotenv 1.1 (Environment config)       |
| - Django REST Framework 3.16 (API Layer)         | - tqdm (Progress utilities)                    |
| - SQLite 3 / psycopg 3.2 (Relational Database)   |                                                |
| - PyMuPDF / fitz 1.26 (PDF Parsing & Cropping)   | DEVELOPMENT & TEST TOOLS                       |
| - BeautifulSoup4 & lxml (HTML Parsing & DOM)     | - Vite 8.1 (Dev Server & Bundler)              |
| - xhtml2pdf / pisa (PDF Rendering Engine)        | - Pytest & Pytest-Django (Backend Testing)     |
| - Django File Storage System (Media Handling)    | - ESLint 10 (Frontend Code Quality)            |
+--------------------------------------------------+------------------------------------------------+
```

---

## 2. Core Technologies

### 2.1. Frontend Framework: React 19 (`react`, `react-dom`)

* **What it is**: The latest major release of React, a declarative JavaScript library for building component-based single-page user interfaces.
* **Where it is used**: Powers the entire client-side application located in `frontend/src/`. All user interface pages (`frontend/src/pages/`) and reusable UI components (`frontend/src/components/`) are written as React functional components with Hooks (`useState`, `useEffect`, `useMemo`, `useCallback`, `useRef`).
* **Responsibility**:
  1. Managing reactive client state (e.g., live filter changes on the Generate page, active editing state on the Review page, polling intervals on the Processing page).
  2. Rendering virtual DOM trees and diffing updates efficiently.
  3. Handling user interactions, synthetic DOM events, file drop zones, and dynamic modal dialogs.
* **How it fits together**: React components interact with backend REST endpoints via service modules in `frontend/src/services/` using Axios. React renders the layout defined in `frontend/src/components/layout/MainLayout.jsx` and switches views through React Router.
* **Why it is suitable**: React's component model and hook-driven state management allow complex, reactive views (such as a live-updating paper generation preview and inline question editor with unsaved-change blocking) to remain cleanly isolated, fast, and maintainable.

---

### 2.2. Client-Side Routing: React Router v7 (`react-router-dom`)

* **What it is**: The standard routing library for React single-page applications, enabling declarative client-side navigation without full-page browser reloads.
* **Where it is used**: Configured in `frontend/src/router/AppRouter.jsx` using `createBrowserRouter` and `RouterProvider`.
* **Responsibility**:
  1. Mapping browser URLs to specific page components:
     * `/` -> `frontend/src/pages/Home.jsx`
     * `/subjects` -> `frontend/src/pages/Subjects.jsx`
     * `/upload` -> `frontend/src/pages/Upload.jsx`
     * `/processing/:documentId` -> `frontend/src/pages/Processing.jsx`
     * `/review/:documentId` -> `frontend/src/pages/Review.jsx`
     * `/generate` -> `frontend/src/pages/Generate.jsx`
  2. Managing route parameters (e.g., extracting `documentId` via `useParams()`).
  3. Providing navigation blocking through `useBlocker` in `frontend/src/pages/Review.jsx` to prevent accidental navigation when a user has unsaved question/chapter edits.
* **How it fits together**: Wraps `MainLayout`, rendering a sticky header and sidebar while swapping out the `<Outlet />` with the active page.
* **Why it is suitable**: React Router v7 provides modern data-router primitives like `useBlocker`, which is essential in an administrative workflow where losing in-progress edits to long questions or answers would degrade the user experience.

---

### 2.3. HTTP Client: Axios (`axios`)

* **What it is**: A promise-based HTTP client for the browser and Node.js with built-in request/response transformation and error handling.
* **Where it is used**: Initialized as a centralized client instance in `frontend/src/services/api.js` and consumed across `subjectService.js`, `documentService.js`, `questionService.js`, and `paperService.js`.
* **Responsibility**:
  1. Sending asynchronous HTTP requests (`GET`, `POST`, `PATCH`, `DELETE`) from the browser to the Django backend.
  2. Standardizing base API routing (`baseURL: '/api/v1'`) and JSON request headers.
  3. Handling `multipart/form-data` file uploads with `onUploadProgress` callbacks to provide live upload percentage feedback.
  4. Handling binary streaming responses (`responseType: 'blob'`) for PDF downloads.
* **How it fits together**: Vite proxies frontend `/api` calls from port `5173` to `http://localhost:8000`. Axios sends requests through this proxy, receives JSON or binary payloads from Django REST Framework views, and unpacks the data into React component state.
* **Why it is suitable**: Axios cleanly handles binary blob streaming (essential for question paper and answer sheet PDF downloads) and progress tracking for large multi-megabyte PDF uploads.

---

### 2.4. Styling: Vanilla CSS & Custom Design System

* **What it is**: Pure standard CSS3 utilizing custom properties (CSS variables), Flexbox, CSS Grid, and scoped component stylesheets.
* **Where it is used**: Global theme variables defined in `frontend/src/index.css`, layout styles in `frontend/src/components/layout/`, and component-specific stylesheets (e.g., `Generate.css`, `Review.css`, `Subjects.css`, `Upload.css`).
* **Responsibility**:
  1. Defining the design tokens (color palettes, shadows, border radii, transitions, typography).
  2. Implementing responsive layouts (sidebars, card grids, floating action bars, modals).
  3. Styling specialized document content (tables, math formula visual containers, badges, working notes).
* **How it fits together**: Imported directly into JSX files. CSS classes match DOM nodes generated by React components and raw HTML strings delivered from the backend.
* **Why it is suitable**: Vanilla CSS gives complete control over printing and rendering rules without build-step overhead or framework constraints, ensuring identical visual presentation between the web UI and generated PDF documents.

---

### 2.5. Backend Web Framework: Django (`Django`)

* **What it is**: A high-level Python web framework that follows the Model-View-Template (MVT) / Model-View-Controller (MVC) architectural pattern.
* **Where it is used**: Configured in `backend/TestSeries/` with modular Django applications in `backend/apps/`:
  * `apps.syllabus` (Subject & Chapter models, views, serializers)
  * `apps.documents` (Document upload, tracking, storage management)
  * `apps.extraction` (Parsing pipelines, pattern matching, Celery tasks)
  * `apps.papers` (Question bank, selection engine, PDF renderers)
  * `apps.accounts` (User model configuration)
  * `apps.common` (Shared utilities)
* **Responsibility**:
  1. Providing the core object-relational mapping (ORM) layer for database interactions.
  2. Managing transaction boundaries (`transaction.atomic()`, `transaction.on_commit()`) for atomic operations and deletions.
  3. Handling file system storage via `django.core.files.storage.default_storage`.
  4. Routing incoming HTTP requests from `backend/TestSeries/urls.py` down to app-level URL configurations.
* **How it fits together**: Acts as the backend backbone, hosting the REST API, executing business logic services, coordinating Celery background tasks, and reading/writing to the database.
* **Why it is suitable**: Django's built-in ORM with support for atomic transactions, foreign keys, cascade safety rules (`PROTECT`), and robust file storage abstractions makes it ideal for handling educational datasets and complex document extraction workflows.

---

### 2.6. REST API Framework: Django REST Framework (`djangorestframework`)

* **What it is**: A powerful, flexible toolkit for building Web APIs in Django.
* **Where it is used**: Across all backend view modules:
  * `backend/apps/syllabus/views.py` & `serializers.py`
  * `backend/apps/documents/views.py` & `serializers.py`
  * `backend/apps/extraction/views.py` & `serializers.py`
  * `backend/apps/papers/views.py` & `serializers.py`
* **Responsibility**:
  1. Serializing ORM instances into JSON payloads and deserializing incoming JSON/FormData into validated Python dictionaries.
  2. Enforcing field validation, cross-field validation, and duplicate checks before data touches the database.
  3. Providing class-based API views (`ModelViewSet`, `ListAPIView`, `RetrieveUpdateDestroyAPIView`, `APIView`).
  4. Standardizing HTTP status codes (`200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `500 Internal Server Error`).
* **How it fits together**: Requests routed from `TestSeries/urls.py` hit DRF viewsets and views. DRF invokes serializers to validate input, runs business logic or service calls, and returns `Response` objects formatted as JSON or streaming binary data (`HttpResponse`).
* **Why it is suitable**: DRF decouples business validation from the database models, enabling complex validation rules (like cross-checking whether a chapter belongs to the selected subject or enforcing module-specific constraints) before executing database operations.

---

### 2.7. Database Layer: SQLite & PostgreSQL Driver (`sqlite3` / `psycopg`)

* **What it is**: SQLite is a serverless, zero-configuration SQL database engine used as the primary active database in `backend/TestSeries/settings.py`. `psycopg` is the PostgreSQL database adapter included in `requirements.txt` for production readiness.
* **Where it is used**: Stores all application relational entities in `backend/db.sqlite3`.
* **Responsibility**:
  1. Persisting subjects, chapters, keywords, documents, extraction logs, and questions.
  2. Enforcing database-level constraints:
     * `unique_subject_name_exam_level` on `Subject`
     * `unique_subject_chapter` on `Chapter`
     * `unique_question_hierarchy_per_document` on `Question`
  3. Indexing foreign keys and search columns (`idx_question_document`, `idx_question_chapter`, `idx_question_parent`, `idx_question_type`).
* **How it fits together**: Accessed exclusively through the Django ORM.
* **Why it is suitable**: SQLite requires zero setup for local development and testing while fully supporting foreign keys, atomic transactions, unique constraints, and B-tree indexes.

---

### 2.8. PDF Parsing & Extraction: PyMuPDF / fitz (`pymupdf`)

* **What it is**: A high-performance Python binding for the MuPDF library, capable of fast PDF page rendering, text extraction with coordinates, vector graphic analysis, and raster pixmap creation.
* **Where it is used**: Inside `backend/apps/extraction/services/`:
  * `pdf_loader.py` (`load_pdf`)
  * `text_extractor.py` (`extract_text`, `detect_headers_footers`, `find_standalone_equation_regions`)
  * `table_processing.py` (`TableProcessor.process_document`)
* **Responsibility**:
  1. Opening PDF files in-memory (`fitz.open(path)`).
  2. Extracting text blocks with exact bounding box coordinates (`x0, y0, x1, y1`).
  3. Detecting table bounding boxes natively via `page.find_tables()`.
  4. Inspecting vector drawing paths (`page.get_drawings()`) to identify mathematical fraction lines and equation boundaries.
  5. Rendering high-resolution raster image crops (`page.get_pixmap(matrix=200/72, 200/72, clip=rect)`) for visual tables and formulas, saving them as PNG files to `media/table_crops/` and `media/formula_crops/`.
* **How it fits together**: Acts as the first stage of the extraction pipeline. It converts raw PDF pages into structured text tokens and image crops, passing them to the downstream layout detector and parsers.
* **Why it is suitable**: PyMuPDF is orders of magnitude faster than pure-Python PDF parsers (like PyPDF2) and provides vector drawing inspection and raster clipping needed to capture complex financial tables and formulas without quality loss.

---

### 2.9. HTML Parsing & DOM Manipulation: BeautifulSoup4 & lxml (`beautifulsoup4`, `lxml`)

* **What it is**: A Python library for parsing HTML documents into searchable, mutable DOM trees, powered by the C-based `lxml` parser backend.
* **Where it is used**:
  * `backend/apps/papers/services/question_selector.py` (`build_group`)
  * `backend/apps/extraction/services/html_formatter.py` (`sanitize_stored_html_table`)
* **Responsibility**:
  1. Parsing stored question/answer HTML content.
  2. Extracting and isolating shared context blocks (`<div class="shared-context">`) from question text and removing them via `ctx_div.decompose()`.
  3. Sanitizing stored HTML tables, cleaning duplicate headers, stripping PyMuPDF artifact columns (`Col1`, `Col2`), and restructuring financial balance sheets.
* **How it fits together**: Sits between the database and the PDF rendering engine. When questions are loaded from the database for practice paper generation, BeautifulSoup parses their HTML once, extracts shared case study text into DTO fields, and ensures clean HTML reaches the renderer.
* **Why it is suitable**: Provides robust DOM manipulation methods (`find`, `decompose`, `find_all`) that make HTML transformation deterministic and resilient to malformed tags.

---

### 2.10. PDF Rendering & Generation: xhtml2pdf / pisa (`xhtml2pdf`)

* **What it is**: A pure-Python HTML/CSS to PDF converter library based on ReportLab.
* **Where it is used**: `backend/apps/papers/services/pdf_renderer.py` (`_html_to_pdf`, `render_question_paper`, `render_answer_sheet`).
* **Responsibility**:
  1. Parsing complete HTML5/CSS documents into PDF print structures.
  2. Handling `@page` rules (A4 portrait size, page margins).
  3. Laying out text, metadata header blocks, dividers, questions, sub-questions, and marks.
  4. Rendering embedded visual image crops (`<img>` tags referencing table and formula crops) and HTML tables (`<table>`, `<thead>`, `<tbody>`).
  5. Producing binary PDF bytes in memory (`io.BytesIO`).
* **How it fits together**: Receives clean HTML generated from `QuestionGroup` DTOs, resolves local image paths from `/media/`, handles rupee glyph substitution (`Rs.`), converts the HTML to PDF bytes, and returns them to the Django view.
* **Why it is suitable**: Unlike WeasyPrint (which requires native C libraries like GTK, Pango, and Cairo that require complex installation on Windows), `xhtml2pdf` is pure Python and runs natively on Windows without external system dependencies.

---

## 3. Supporting Libraries

### 3.1. Asynchronous Task Queue: Celery & Redis (`celery`, `redis`)

* **What it is**: Celery is a distributed task queue system; Redis is an in-memory data store acting as the Celery message broker.
* **Where it is used**:
  * Configured in `backend/TestSeries/settings.py` (`CELERY_BROKER_URL`)
  * Defined in `backend/apps/extraction/tasks.py` (`extract_document_task`)
  * Triggered in `backend/apps/documents/views.py` (`DocumentUploadView.perform_create`)
* **Responsibility**:
  1. Offloading heavy, long-running PDF extraction jobs (which can take 5–30 seconds for 50-page PDFs) from the synchronous HTTP request/response cycle.
  2. Managing task retries on operational errors with exponential backoff (`acks_late=True`, `max_retries=5`).
* **How it fits together**: When a PDF is uploaded, the view saves the document record and calls `extract_document_task.delay(document_id)`. The task message is pushed to Redis. A Celery worker dequeues the task and runs `ExtractionService.trigger_extraction()`. Meanwhile, the HTTP upload endpoint returns immediately with status `PENDING`, allowing the frontend to poll status via `/processing/:documentId`.
* **Why it is suitable**: Prevents HTTP request timeouts and server thread starvation during heavy PDF extraction and image rendering tasks.

---

### 3.2. Image Processing & OCR Stack: Pillow & OpenCV (`Pillow`, `opencv-python`, `pytesseract`)

* **What it is**: Python imaging and computer vision libraries.
* **Where it is used**: Declared in `requirements.txt` as supporting components for image manipulation, OCR fallback preprocessing, and image format conversion.
* **Responsibility**: Handling raster operations, image dimension scaling, and noise filtering if OCR processing is invoked on scanned pages.
* **How it fits together**: Works alongside PyMuPDF when extracting or verifying visual image crops.

---

### 3.3. Environment Configuration: python-dotenv (`python-dotenv`)

* **What it is**: Loads environment variables from a `.env` file into `os.environ`.
* **Where it is used**: Declared in `requirements.txt` to support local configuration overrides (e.g., custom `CELERY_BROKER_URL`, database credentials, debug flags).

---

### 3.4. Frontend Iconography: React Icons (`react-icons`)

* **What it is**: An icon library bundling popular icon packages (Feather, FontAwesome, Material Icons) as modular React components.
* **Where it is used**: Used across navigation menus, status indicators, badges, and action buttons in `frontend/src/components/` and `frontend/src/pages/`.

---

## 4. Development & Testing Tools

* **Vite 8.1 (`vite`, `@vitejs/plugin-react`)**: Modern frontend development server and bundler. Provides Hot Module Replacement (HMR) during development and bundles production assets. Configured in `frontend/vite.config.js` with API reverse-proxying.
* **Pytest & Pytest-Django (`pytest`, `pytest-django`)**: Test execution framework for running automated unit and integration tests across Django applications (`backend/apps/*/tests.py`).
* **ESLint (`eslint`)**: Static analysis tool for identifying JavaScript and React syntax issues, hook dependency errors, and code quality issues.

---

## 5. End-to-End Technology Communication Pipeline

```
+---------------------------------------------------------------------------------------------------+
| 1. USER INTERACTION (Browser / React 19)                                                          |
|    - User interacts with UI (Upload PDF, Edit Questions, Configure Practice Paper Filters)       |
|    - Component state updates -> Validated locally -> Dispatched via Axios                          |
+---------------------------------------------------------------------------------------------------+
                                              |  HTTP (JSON / Multipart / Binary)
                                              v
+---------------------------------------------------------------------------------------------------+
| 2. API & REVERSE PROXY (Vite Dev Server -> Django REST Framework)                                 |
|    - Vite proxies '/api/v1/*' to 'http://localhost:8000/api/v1/*'                                 |
|    - Django URL Router -> ViewSets / Views (SubjectViewSet, DocumentUploadView, GenerateView)    |
|    - Serializers validate inputs (DocumentUploadSerializer, GenerationFilterSerializer)            |
+---------------------------------------------------------------------------------------------------+
                                              |
                       +----------------------+----------------------+
                       |                                             |
                       v                                             v
+------------------------------------------+  +----------------------------------------------------+
| 3A. ASYNCHRONOUS EXTRACTION PIPELINE     |  | 3B. ON-DEMAND PRACTICE PAPER GENERATION             |
|    - View queues Celery Task via Redis   |  |    - GeneratePreviewView calls                      |
|    - Celery Worker runs ExtractionService|  |      select_question_groups()                       |
|    - PyMuPDF (fitz) extracts text/crops  |  |    - QuestionSelector queries Question ORM model    |
|    - Parsers extract Questions & Answers |  |    - BeautifulSoup parses shared context HTML once  |
|    - ChapterMapper maps topics           |  |    - Randomized best-fit algorithm selects groups   |
|    - HTMLFormatter normalizes content    |  |    - Selected root question IDs returned to React   |
|    - Saves Question records to SQLite    |  +----------------------------------------------------+
+------------------------------------------+                             |
                       |                                                 | User clicks "Download"
                       v                                                 v
+---------------------------------------------------------------------------------------------------+
| 4. DATABASE & MEDIA PERSISTENCE                                                                   |
|    - SQLite (`backend/db.sqlite3`): Subject, Chapter, Document, ExtractionLog, Question records   |
|    - Media Storage (`media/`): Uploaded PDFs (`documents/`), Table crops (`table_crops/`),         |
|      Formula crops (`formula_crops/`)                                                             |
+---------------------------------------------------------------------------------------------------+
                                              |
                                              v
+---------------------------------------------------------------------------------------------------+
| 5. PDF RENDERING ENGINE (xhtml2pdf / pisa)                                                        |
|    - GenerateQuestionPaperView / GenerateAnswerSheetView receives root question IDs               |
|    - pdf_renderer.py builds clean A4 print HTML (deduplicating shared contexts & styling tables) |
|    - Resolves '/media/' image crop paths to local disk files                                      |
|    - xhtml2pdf compiles HTML + CSS into raw binary PDF bytes in memory (no disk write)           |
+---------------------------------------------------------------------------------------------------+
                                              |
                                              v
+---------------------------------------------------------------------------------------------------+
| 6. STREAMING DOWNLOAD & CLIENT SAVE                                                               |
|    - Django returns HttpResponse with 'application/pdf' and 'Content-Disposition: attachment'     |
|    - Axios receives Binary Blob -> Creates window.URL.createObjectURL(blob)                       |
|    - Synthetic <a> element clicked -> PDF downloaded to user's device                            |
+---------------------------------------------------------------------------------------------------+
```
