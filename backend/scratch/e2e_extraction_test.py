"""
End-to-End Extraction Test
==========================
Tests upload + extraction for each document listed in situation.md.
Runs directly against Django ORM (no HTTP server needed).
Compares extraction results with PDF ground truth using pdfplumber.

Run from backend/ directory:
    ..\.venv\Scripts\python.exe scratch/e2e_extraction_test.py
"""
import os
import sys
import re
import time
import json
import datetime
import traceback

# Django setup must happen before other imports
import django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TestSeries.settings")
django.setup()

import pdfplumber
from apps.documents.models import Document
from apps.syllabus.models import Subject
from apps.papers.models import Question
from apps.extraction.services.extraction_pipeline import extract_document

# ── Configuration ─────────────────────────────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.normpath(os.path.join(BACKEND_DIR, "..", "docs"))

TEST_DOCUMENTS = [
    {
        "pdf": "rtp-may-2026-aa.pdf",
        "subject_id": 3,
        "title": "AA May 2026 RTP",
        "document_type": "RTP",
        "paper_year": 2026,
        "exam_month": "May",
        "expected_q_min": 5,
    },
    {
        "pdf": "rtp-may-2024-afm.pdf",
        "subject_id": 1,
        "title": "AFM May 2024 RTP",
        "document_type": "RTP",
        "paper_year": 2024,
        "exam_month": "May",
        "expected_q_min": 5,
    },
    {
        "pdf": "rtp-may-2026-dt.pdf",
        "subject_id": 4,
        "title": "DT May 2026 RTP",
        "document_type": "RTP",
        "paper_year": 2026,
        "exam_month": "May",
        "expected_q_min": 5,
    },
    {
        "pdf": "rtp-may-2024-fr.pdf",
        "subject_id": 2,
        "title": "FR May 2024 RTP",
        "document_type": "RTP",
        "paper_year": 2024,
        "exam_month": "May",
        "expected_q_min": 5,
    },
    {
        "pdf": "rtp-may-2026-fr.pdf",
        "subject_id": 2,
        "title": "FR May 2026 RTP",
        "document_type": "RTP",
        "paper_year": 2026,
        "exam_month": "May",
        "expected_q_min": 5,
    },
    {
        "pdf": "rtp-may-2026-ibs.pdf",
        "subject_id": 5,
        "title": "IBS May 2026 RTP",
        "document_type": "RTP",
        "paper_year": 2026,
        "exam_month": "May",
        "expected_q_min": 5,
    },
    {
        "pdf": "rtp-may-2026-it.pdf",
        "subject_id": 6,
        "title": "ITL May 2026 RTP",
        "document_type": "RTP",
        "paper_year": 2026,
        "exam_month": "May",
        "expected_q_min": 5,
    },
]


# ── PDF Ground Truth Extraction ───────────────────────────────────────────────
def get_pdf_page_count(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0


def extract_pdf_question_numbers(pdf_path):
    """
    Extracts top-level Q-numbers from a PDF.
    Looks for patterns like: Question 1, Q.1, Q1 at line start.
    Returns sorted list of unique integer question numbers found.
    """
    q_patterns = [
        re.compile(r'(?m)^Question\s+(\d+)\b', re.IGNORECASE),
        re.compile(r'(?m)^\s*Q\.?\s*(\d+)\b', re.IGNORECASE),
    ]
    found_nums = set()
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for pat in q_patterns:
                    for m in pat.finditer(text):
                        n = int(m.group(1))
                        if 1 <= n <= 30:
                            found_nums.add(n)
    except Exception as e:
        print(f"  [WARN] pdfplumber error on {pdf_path}: {e}")
    return sorted(found_nums)


def get_pdf_text_sample(pdf_path, pages=5):
    """Returns first N pages of text from PDF."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            texts = []
            for i, page in enumerate(pdf.pages[:pages]):
                texts.append(f"--- Page {i+1} ---\n{page.extract_text() or ''}")
            return "\n".join(texts)
    except Exception as e:
        return f"[Error reading PDF: {e}]"


# ── Test Runner ───────────────────────────────────────────────────────────────
def run_test(doc_cfg):
    pdf_filename = doc_cfg["pdf"]
    pdf_path = os.path.join(DOCS_DIR, pdf_filename)
    title = doc_cfg["title"]

    print(f"\n{'='*60}")
    print(f"Testing: {title}")
    print(f"PDF: {pdf_path}")
    print(f"{'='*60}")

    result = {
        "title": title,
        "pdf": pdf_filename,
        "status": "UNKNOWN",
        "extraction_status": None,
        "questions_extracted": 0,
        "top_level_questions": 0,
        "sub_questions": 0,
        "questions_with_answers": 0,
        "questions_without_answers": 0,
        "pdf_page_count": 0,
        "pdf_q_numbers": [],
        "db_q_numbers": [],
        "unmatched_q_numbers": [],
        "errors": [],
        "warnings": [],
        "sample_questions": [],
        "extraction_time_s": None,
    }

    # 1. Check PDF exists
    if not os.path.exists(pdf_path):
        result["status"] = "SKIP"
        result["errors"].append(f"PDF not found: {pdf_path}")
        print(f"  [SKIP] PDF not found at {pdf_path}")
        return result

    # 2. PDF Ground Truth
    print("  [1/4] Extracting PDF ground truth...")
    result["pdf_page_count"] = get_pdf_page_count(pdf_path)
    pdf_q_nums = extract_pdf_question_numbers(pdf_path)
    result["pdf_q_numbers"] = pdf_q_nums
    print(f"  PDF pages: {result['pdf_page_count']}")
    print(f"  PDF top-level Q-numbers found: {pdf_q_nums}")

    # 3. Setup Document record
    print("  [2/4] Setting up Document record...")
    try:
        subject = Subject.objects.get(pk=doc_cfg["subject_id"])
    except Subject.DoesNotExist:
        result["status"] = "ERROR"
        result["errors"].append(f"Subject ID {doc_cfg['subject_id']} not found")
        print("  [ERROR] Subject not found")
        return result

    # Clean re-test: delete any existing document with the same title
    existing_docs = Document.objects.filter(title=title)
    if existing_docs.exists():
        count = existing_docs.count()
        existing_docs.delete()
        print(f"  Deleted {count} existing record(s) for clean re-test")

    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.first()
    if user is None:
        user, _ = User.objects.get_or_create(
            username="system_user",
            defaults={"email": "system@example.com"}
        )

    doc = Document.objects.create(
        user=user,
        subject=subject,
        title=title,
        document_type=doc_cfg["document_type"],
        paper_year=doc_cfg["paper_year"],
        exam_month=doc_cfg["exam_month"],
        storage_path=pdf_path,
        extraction_status=Document.ExtractionStatus.PENDING,
    )
    print(f"  Created Document ID={doc.document_id} | Subject: {subject.name}")

    # 4. Run Extraction
    print("  [3/4] Running extraction pipeline (this may take a minute)...")
    start_t = time.time()
    try:
        extract_document(doc, temp_file_path=pdf_path)
        elapsed = time.time() - start_t
        result["extraction_time_s"] = round(elapsed, 2)
        doc.refresh_from_db()
        result["extraction_status"] = doc.extraction_status
        print(f"  Extraction finished: status={doc.extraction_status} | time={elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - start_t
        result["extraction_time_s"] = round(elapsed, 2)
        result["status"] = "ERROR"
        result["errors"].append(f"Exception [{type(e).__name__}]: {str(e)[:300]}")
        result["extraction_status"] = "EXCEPTION"
        print(f"  [ERROR] Exception during extraction: {type(e).__name__}: {e}")
        traceback.print_exc()
        return result

    # 5. Analyze Results
    print("  [4/4] Analyzing extraction results...")
    questions = Question.objects.filter(document=doc).select_related("chapter")
    total_q = questions.count()
    top_level = questions.filter(parent_question__isnull=True)
    sub_q_count = questions.filter(parent_question__isnull=False).count()
    with_answer = questions.exclude(answer_text="").count()
    without_answer = questions.filter(answer_text="").count()

    result["questions_extracted"] = total_q
    result["top_level_questions"] = top_level.count()
    result["sub_questions"] = sub_q_count
    result["questions_with_answers"] = with_answer
    result["questions_without_answers"] = without_answer

    db_q_numbers = sorted(set(q.question_number for q in top_level))
    result["db_q_numbers"] = db_q_numbers

    print(f"  Extracted: {total_q} total ({top_level.count()} top-level, {sub_q_count} sub-questions)")
    print(f"  With answers: {with_answer} | Without answers: {without_answer}")
    print(f"  DB Q-numbers: {db_q_numbers}")

    # Compare against PDF
    pdf_q_set = set(str(n) for n in pdf_q_nums)
    db_q_set = set(db_q_numbers)
    missing_in_db = sorted(pdf_q_set - db_q_set)
    extra_in_db = sorted(db_q_set - pdf_q_set)
    result["unmatched_q_numbers"] = missing_in_db
    result["extra_q_numbers_in_db"] = extra_in_db

    if missing_in_db:
        msg = f"Q-numbers in PDF but missing from DB: {missing_in_db}"
        result["warnings"].append(msg)
        print(f"  [WARN] {msg}")
    if extra_in_db:
        msg = f"Q-numbers in DB but NOT in PDF (false positives?): {extra_in_db}"
        result["warnings"].append(msg)
        print(f"  [WARN] {msg}")

    # Sample top-level questions
    sample_qs = top_level.order_by("question_number")[:6]
    for sq in sample_qs:
        sample_entry = {
            "q_number": sq.question_number,
            "chapter": sq.chapter.chapter_name if sq.chapter else None,
            "question_type": sq.question_type,
            "marks": sq.marks,
            "has_answer": bool(sq.answer_text.strip()) if sq.answer_text else False,
            "q_preview": (sq.question_text or "")[:250].replace("\n", " ").strip(),
            "a_preview": (sq.answer_text or "")[:200].replace("\n", " ").strip(),
        }
        result["sample_questions"].append(sample_entry)

    # Determine PASS/PARTIAL/FAIL
    min_q = doc_cfg.get("expected_q_min", 5)
    completed = (doc.extraction_status == Document.ExtractionStatus.COMPLETED)
    sufficient_qs = (total_q >= min_q)
    has_answers = (with_answer > 0)

    if completed and sufficient_qs and has_answers and not missing_in_db:
        result["status"] = "PASS"
    elif completed and sufficient_qs and has_answers:
        result["status"] = "PARTIAL"
    elif doc.extraction_status == Document.ExtractionStatus.FAILED:
        result["status"] = "FAIL"
    elif not sufficient_qs:
        result["status"] = "FAIL"
        result["errors"].append(f"Only {total_q} questions, expected >= {min_q}")
    else:
        result["status"] = "PARTIAL"

    print(f"  Result: {result['status']}")
    return result


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  TestSeries End-to-End Extraction Test")
    print(f"  Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Docs dir: {DOCS_DIR}")
    print("=" * 70)

    all_results = []
    for doc_cfg in TEST_DOCUMENTS:
        try:
            res = run_test(doc_cfg)
        except Exception as e:
            res = {
                "title": doc_cfg.get("title", doc_cfg["pdf"]),
                "pdf": doc_cfg["pdf"],
                "status": "ERROR",
                "errors": [f"Unhandled: {type(e).__name__}: {e}"],
                "questions_extracted": 0,
                "top_level_questions": 0,
                "sub_questions": 0,
                "questions_with_answers": 0,
                "questions_without_answers": 0,
                "sample_questions": [],
            }
            traceback.print_exc()
        all_results.append(res)

    # ── Summary Table ─────────────────────────────────────────────────────────
    print(f"\n\n{'='*75}")
    print("END-TO-END EXTRACTION TEST SUMMARY")
    print(f"{'='*75}")
    header = f"{'Document':<24} {'Status':<9} {'Total':<7} {'TopQ':<6} {'SubQ':<6} {'W/Ans':<7} {'W/O':<6}"
    print(header)
    print("-" * 75)
    for r in all_results:
        status_icon = {"PASS": "✓ PASS", "PARTIAL": "~ PART", "FAIL": "✗ FAIL", "ERROR": "! ERR", "SKIP": "- SKIP"}.get(r.get("status", "?"), r.get("status", "?"))
        print(
            f"{r.get('title',''):<24} "
            f"{status_icon:<9} "
            f"{r.get('questions_extracted', '?'):<7} "
            f"{r.get('top_level_questions', '?'):<6} "
            f"{r.get('sub_questions', '?'):<6} "
            f"{r.get('questions_with_answers', '?'):<7} "
            f"{r.get('questions_without_answers', '?'):<6}"
        )
        if r.get("errors"):
            for e in r["errors"]:
                print(f"    [ERROR] {e}")
        if r.get("warnings"):
            for w in r["warnings"]:
                print(f"    [WARN]  {w}")

    counts = {"PASS": 0, "PARTIAL": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for r in all_results:
        s = r.get("status", "ERROR")
        counts[s] = counts.get(s, 0) + 1
    print(f"\n{'='*75}")
    print(f"PASS: {counts['PASS']}  PARTIAL: {counts['PARTIAL']}  FAIL: {counts['FAIL']}  ERROR: {counts['ERROR']}  SKIP: {counts['SKIP']}")
    print(f"{'='*75}")

    # ── Sample Questions ──────────────────────────────────────────────────────
    print(f"\n\n{'='*75}")
    print("SAMPLE EXTRACTED QUESTIONS (first 5 top-level per doc)")
    print(f"{'='*75}")
    for r in all_results:
        print(f"\n{'─'*60}")
        print(f"  {r.get('title')}  [{r.get('status')}]")
        print(f"  PDF Q-nums: {r.get('pdf_q_numbers', [])} | DB Q-nums: {r.get('db_q_numbers', [])}")
        print(f"{'─'*60}")
        samples = r.get("sample_questions", [])
        if not samples:
            print("  (no questions extracted)")
        for sq in samples:
            ans_flag = "✓" if sq.get("has_answer") else "✗"
            print(f"  Q{sq.get('q_number'):>3} | type={sq.get('question_type','?'):<12} | {sq.get('marks','?')}m | ans={ans_flag} | ch={sq.get('chapter','?')}")
            q_prev = sq.get("q_preview", "")[:120]
            a_prev = sq.get("a_preview", "")[:100]
            print(f"       Q: {q_prev}")
            if a_prev:
                print(f"       A: {a_prev}")

    # ── Save JSON Report ──────────────────────────────────────────────────────
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n\nDetailed JSON report saved to:\n  {report_path}")


if __name__ == "__main__":
    main()
