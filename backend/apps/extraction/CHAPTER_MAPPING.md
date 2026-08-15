# Question Chapter Mapping System

This document outlines the architecture and behavior of the dynamic question-to-chapter mapping system in the backend extraction pipeline.

---

## 1. How Dynamic Chapter Mapping Works

Chapter mapping is performed during document extraction in `apps/extraction/services/extraction_pipeline.py` using helper logic in `apps/extraction/services/chapter_mapper.py`.

1. **Subject-Based Chapter Lookup**:
   - `get_prepared_chapters(document.subject)` queries `Chapter.objects.filter(subject=document.subject)` dynamically for whatever subject the document belongs to (Financial Reporting, Auditing, Law, Direct Tax, etc.).
   - No chapter names or keywords are hardcoded in the codebase.

2. **Weighted Pattern Construction**:
   For every chapter in the subject, weighted pattern rules are generated at runtime:
   - **Full Chapter Name** (e.g. `Ind AS 110: Consolidated Financial Statements` or `SA 240: Fraud Responsibilities`): **Weight = 5**
   - **Designation Code Prefix** (e.g. `Ind AS 110`, `SA 240`, `AS 16`, `Chapter 3`): **Weight = 3**
   - **Topic Title** (e.g. `Consolidated Financial Statements`, `Fraud Responsibilities`): **Weight = 2**
   - **Custom Keywords** (from `ChapterKeyword` record if present): **Weight = 1**

3. **Pre-Question Header Text Scanning**:
   - For each extracted question, the pipeline scans candidate text immediately *preceding* the question header (`gap_text` and trailing previous question text).
   - When a chapter section header is found before Question N, `active_chapter` updates to that chapter and persists for questions in that section until a new chapter heading appears.

4. **Parent & Shared-Context Inheritance**:
   - Sub-questions (`8.i`, `8.ii`, `12.i`, `12.ii`) inherit their parent question's mapped chapter.
   - Case scenario question groups sharing the same `shared-context` block receive unified chapter assignment.

---

## 2. Future Scope Note: RTP Restriction

> **Note**: Automatic chapter mapping currently runs for all documents processed by the extraction pipeline. If a future release restricts automatic chapter mapping strictly to RTP (Revision Test Paper) document uploads, a document type check can be added in `extraction_pipeline.py`:
> ```python
> if getattr(document, 'document_type', None) == 'RTP':
>     prepared_chapters = get_prepared_chapters(document.subject)
> else:
>     prepared_chapters = []
> ```
