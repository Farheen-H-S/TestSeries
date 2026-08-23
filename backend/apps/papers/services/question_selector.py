"""
Question selector service for paper generation.

Responsibilities:
- Build QuestionGroup DTOs from database Question records
- Run best-fit randomized selection
- Fetch groups by ordered ID list (for PDF endpoints)

All HTML parsing happens exactly once inside build_group().
Renderers receive fully-assembled DTOs and make zero DB calls.
"""
import re
import random
import logging
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup
from django.conf import settings
from django.db.models import Prefetch

from apps.papers.models import Question

logger = logging.getLogger(__name__)

# Configurable via Django settings — easy to tune without touching logic
SELECTION_ATTEMPTS: int = getattr(settings, 'PAPER_SELECTION_ATTEMPTS', 100)


# ---------------------------------------------------------------------------
# Content pre-rendering
# ---------------------------------------------------------------------------

def _prerender_html_content(content: str) -> str:
    """
    Convert stored question/answer content to render-ready HTML.

    Stored content may be in one of two states:

    1. Pre-rendered HTML (from earlier extractions) — contains <table> HTML that
       may have dummy PyMuPDF headers (Col1, Col2) or 15 vertical empty columns.
       We sanitize this via clean_stored_html_tables().
    2. Hybrid HTML: <p> tags wrapping raw text that still contains
       [STRUCTURED_START]...[STRUCTURED_END] markdown table blocks.
       We convert this via markdown_table_to_html().
    """
    if not content:
        return ''

    from apps.extraction.services.html_formatter import markdown_table_to_html, clean_stored_html_tables

    result = content

    if '[STRUCTURED_START]' in result:
        def _render_table_block(m):
            inner = m.group(1).strip()
            # If inner is already rendered HTML (e.g. formula-container, table-container with img, or table), preserve it
            if inner.startswith('<div') or '<img' in inner or '<table' in inner:
                return inner

            # Strip HTML tags that preserve_paragraphs may have wrapped around the markdown
            inner_clean = re.sub(r'<[^>]+>', '', inner)
            # Unescape HTML entities so the markdown parser sees clean text
            inner_clean = inner_clean.replace('&lt;br&gt;', '<br>').replace('&lt;br/&gt;', '<br>').replace('&lt;br /&gt;', '<br>')
            inner_clean = inner_clean.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            inner_clean = inner_clean.strip()
            if not inner_clean:
                return ''
            try:
                return markdown_table_to_html(inner_clean)
            except Exception as exc:
                logger.warning(
                    "Table pre-rendering failed in build_group; falling back to empty: %s", exc
                )
                return ''

        result = re.sub(
            r'\[STRUCTURED_START\](.*?)\[STRUCTURED_END\]',
            _render_table_block,
            result,
            flags=re.DOTALL,
        )

        # Clean up empty <p></p> tags left behind after replacement
        result = re.sub(r'<p[^>]*>\s*</p>', '', result)

    # Sanitize any <table> elements (whether newly generated or stored in DB)
    if '<table' in result:
        result = clean_stored_html_tables(result)

    # Unescape &lt;br&gt; in regular non-table text as well
    result = result.replace('&lt;br&gt;', '<br />')
    result = result.replace('&lt;br/&gt;', '<br />')
    result = result.replace('&lt;br /&gt;', '<br />')

    return result


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

@dataclass
class SubQuestion:
    """A leaf-level sub-question, fully assembled for rendering."""
    question_id: int
    sub_question_label: str     # preserved exactly from DB (e.g. "a", "i", "ii")
    question_html: str
    answer_html: str
    marks: Optional[int]


@dataclass
class QuestionGroup:
    """
    An atomic unit of generation — a root question and all its sub-questions.

    Shared context is extracted from question_content HTML at build time.
    Renderers never parse HTML.
    """
    root_question_id: int
    question_html: str              # question_content minus the shared-context div
    answer_html: str                # root-level answer (used when group has no sub-questions)
    sub_questions: list             # list[SubQuestion], ordered by hierarchy_key
    total_marks: int                # computed by canonical rule — never double-counts
    shared_context_html: Optional[str]  # extracted from question_content, or None
    subject_name: str
    exam_level: str
    module: str                     # document_type value: RTP | PYQ | MOCK
    document_title: str             # title of original uploaded paper document
    chapter_name: Optional[str] = None # title of mapped chapter if available


@dataclass
class SelectionResult:
    """Output of the selection engine."""
    groups: list                    # list[QuestionGroup], ordered as selected
    total_marks_selected: int
    total_questions_selected: int   # count of root questions selected
    available_marks: int
    available_questions: int
    subject_name: str
    exam_level: str
    module: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _base_queryset():
    """
    Shared queryset used by both select_question_groups and fetch_groups_by_ids.
    Eagerly loads everything renderers need — zero N+1 queries.

    answer_content is a direct column on Question so sub_questions prefetch
    loads answers automatically alongside question data.
    """
    return (
        Question.objects
        .filter(parent_question__isnull=True)
        .select_related('document__subject', 'chapter')
        .prefetch_related(
            Prefetch(
                'sub_questions',
                queryset=Question.objects.order_by('hierarchy_key')
            )
        )
    )


def _is_valid_root(q: Question) -> bool:
    """
    Exclude questions where extraction or review left mandatory fields empty.
    This is a data quality guard — the review page is the approval step,
    so questions with empty content represent incomplete review data.
    Sub-questions are filtered per-group inside build_group().
    """
    return bool(
        q.question_content and q.question_content.strip() and
        q.answer_content and q.answer_content.strip()
    )



def build_group(q: Question) -> QuestionGroup:
    """
    Assemble a QuestionGroup DTO from a root Question ORM instance.

    HTML parsing happens here, once. After this point, renderers are pure
    DTO consumers.

    Marks canonical rule (avoids double-counting):
      If the root question has sub-questions with marks data, the children
      are authoritative (the root mark is just the total label). Otherwise,
      the root mark is used directly.

    Example — ICAI Q1 (16 Marks) with (a)=4, (b)=4, (c)=8:
      child_marks = [4, 4, 8]  → total_marks = 16   (correct, no double-count)

    Example — standalone question Q2 (5 Marks), no sub-questions:
      child_marks = []          → total_marks = 5    (correct)
    """
    # --- Pre-render embedded table blocks in stored content ---
    # Stored question_content may contain [STRUCTURED_START]...[STRUCTURED_END]
    # markdown table blocks that were never converted to HTML during extraction.
    # _prerender_html_content() detects and renders these so the PDF renderer
    # always receives clean, fully-rendered HTML.
    prerendered_content = _prerender_html_content(q.question_content)

    # --- Extract shared context from question_content HTML (once) ---
    soup = BeautifulSoup(prerendered_content, 'html.parser')
    ctx_div = soup.find('div', class_='shared-context')
    shared_context_html = str(ctx_div) if ctx_div else None
    if ctx_div:
        ctx_div.decompose()  # remove from soup in-place
    question_html = str(soup)

    # --- Build sub-questions (ordered by hierarchy_key, filtered for validity) ---
    sub_questions = []
    for sq in q.sub_questions.all():
        # Skip sub-questions with empty content — don't invalidate the whole group
        if not (sq.question_content and sq.question_content.strip()):
            logger.warning(
                "Sub-question %d has empty question_content — excluded from group %d",
                sq.question_id, q.question_id
            )
            continue
        sub_questions.append(SubQuestion(
            question_id=sq.question_id,
            sub_question_label=sq.sub_question_label or '',
            question_html=_prerender_html_content(sq.question_content),
            answer_html=_prerender_html_content(sq.answer_content) if sq.answer_content else '',
            marks=sq.marks,
        ))

    # --- Canonical marks rule ---
    child_marks = [sq.marks for sq in sub_questions if sq.marks is not None]
    if child_marks:
        # Children are authoritative; root mark is a total label — avoid double-counting
        total_marks = sum(child_marks)
    else:
        # Standalone question or root with no child mark data
        total_marks = q.marks or 0

    return QuestionGroup(
        root_question_id=q.question_id,
        question_html=question_html,
        answer_html=_prerender_html_content(q.answer_content) if q.answer_content else '',
        sub_questions=sub_questions,
        total_marks=total_marks,
        shared_context_html=shared_context_html,
        subject_name=q.document.subject.name,
        exam_level=q.document.subject.exam_level,
        module=q.document.document_type,
        document_title=q.document.title,
        chapter_name=q.chapter.chapter_name if q.chapter else None,
    )


def _greedy_select(groups: list, filters: dict):
    """
    Single greedy pass over a pre-shuffled group list.
    Stops when the marks target or question count target is reached.

    Returns (selected_groups, total_marks, total_count).
    """
    total_marks = filters.get('total_marks')
    question_count = filters.get('question_count')

    selected = []
    running_marks = 0
    running_count = 0

    for group in groups:
        if total_marks is not None:
            if running_marks + group.total_marks <= total_marks:
                selected.append(group)
                running_marks += group.total_marks
                running_count += 1
        else:
            if running_count < question_count:
                selected.append(group)
                running_marks += group.total_marks
                running_count += 1
            else:
                break

    return selected, running_marks, running_count


def _closer_to_target(candidate_marks, candidate_count, best_marks, best_count, filters):
    """
    Returns True if the candidate result is closer to the target than the current best.
    For marks-constrained: maximise marks (closest to target without exceeding).
    For count-constrained: maximise count.
    """
    total_marks = filters.get('total_marks')
    if total_marks is not None:
        return candidate_marks > best_marks
    else:
        return candidate_count > best_count


def _perfect_fit(marks, count, filters):
    """Returns True when the selection exactly meets the target."""
    total_marks = filters.get('total_marks')
    if total_marks is not None:
        return marks == total_marks
    return count == filters.get('question_count', 0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_question_groups(filters: dict) -> SelectionResult:
    """
    Find all eligible question groups matching the filters, then run
    best-fit randomized selection to find the combination closest to the
    requested marks or question count.

    Runs SELECTION_ATTEMPTS shuffled greedy passes and keeps the best result.
    Short-circuits as soon as a perfect fit is found.

    Args:
        filters: dict with keys:
            subject_id (int, required)
            module (str, required): 'RTP' | 'PYQ' | 'MOCK'
            chapter_ids (list[int], optional)
            total_marks (int, optional — marks-constrained modules)
            question_count (int, optional — count-constrained modules)
            question_type (str, optional)
            year_from (int, optional)
            year_to (int, optional)
            exam_month (str, optional)
    """
    queryset = _base_queryset().filter(
        document__subject_id=filters['subject_id'],
        document__document_type=filters['module'],
    )

    # Optional filters
    chapter_ids = filters.get('chapter_ids')
    if chapter_ids:
        queryset = queryset.filter(chapter_id__in=chapter_ids)

    question_type = filters.get('question_type')
    if question_type and question_type != 'MIXED':
        queryset = queryset.filter(question_type=question_type)

    year_from = filters.get('year_from')
    year_to = filters.get('year_to')
    if year_from:
        queryset = queryset.filter(document__paper_year__gte=year_from)
    if year_to:
        queryset = queryset.filter(document__paper_year__lte=year_to)

    exam_month = filters.get('exam_month')
    if exam_month:
        queryset = queryset.filter(document__exam_month=exam_month)

    # Build DTOs — HTML parsing happens here, once
    all_groups = [build_group(q) for q in queryset if _is_valid_root(q)]
    available_questions = len(all_groups)
    available_marks = sum(g.total_marks for g in all_groups)

    if not all_groups:
        return SelectionResult(
            groups=[], total_marks_selected=0, total_questions_selected=0,
            available_marks=0, available_questions=0,
            subject_name='', exam_level='', module=filters['module']
        )

    # Best-fit randomized selection
    best_groups, best_marks, best_count = None, 0, 0

    for attempt in range(SELECTION_ATTEMPTS):
        random.shuffle(all_groups)
        candidate, marks, count = _greedy_select(all_groups, filters)
        if best_groups is None or _closer_to_target(marks, count, best_marks, best_count, filters):
            best_groups, best_marks, best_count = candidate, marks, count
        if _perfect_fit(marks, count, filters):
            logger.debug("Perfect fit achieved on attempt %d", attempt + 1)
            break

    first = best_groups[0] if best_groups else all_groups[0]
    return SelectionResult(
        groups=best_groups,
        total_marks_selected=best_marks,
        total_questions_selected=best_count,
        available_marks=available_marks,
        available_questions=available_questions,
        subject_name=first.subject_name,
        exam_level=first.exam_level,
        module=first.module,
    )


def fetch_groups_by_ids(root_question_ids: list) -> list:
    """
    Build QuestionGroup DTOs for a known ordered list of root question IDs.
    Used by PDF endpoints — no random selection, caller-supplied order preserved.

    Returns list[QuestionGroup] in the same order as root_question_ids.
    """
    queryset = _base_queryset().filter(question_id__in=root_question_ids)
    q_map = {q.question_id: build_group(q) for q in queryset}
    return [q_map[qid] for qid in root_question_ids if qid in q_map]
