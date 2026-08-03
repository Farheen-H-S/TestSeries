"""
PDF renderer service for paper generation.

Two independent stateless functions:
  - render_question_paper()
  - render_answer_sheet()

Both receive fully-assembled QuestionGroup DTOs.
Zero database calls. Zero HTML parsing.

Shared context deduplication happens via a local tracking variable in each
render call — question paper and answer sheet deduplicate independently.
"""
import logging
from datetime import date

import io

from xhtml2pdf import pisa

from .question_selector import QuestionGroup

logger = logging.getLogger(__name__)


def _html_to_pdf(html_str: str) -> bytes:
    """
    Convert an HTML string to PDF bytes using xhtml2pdf (pisa).
    xhtml2pdf is pure-Python and works natively on Windows without GTK.
    Raises RuntimeError if conversion produces errors.
    """
    buf = io.BytesIO()
    result = pisa.CreatePDF(html_str, dest=buf)
    if result.err:
        raise RuntimeError(f"PDF conversion failed with {result.err} error(s).")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_date() -> str:
    """Return today's date formatted for PDF display."""
    return date.today().strftime("%-d %B %Y") if hasattr(date.today(), 'strftime') else str(date.today())


def _safe_date() -> str:
    """Cross-platform date formatting."""
    today = date.today()
    # strftime('%e') pads with space; strip it for clean display
    return today.strftime("%d %B %Y").lstrip('0')


def _module_display(module: str) -> str:
    mapping = {
        'RTP': 'Revision Test Paper (RTP)',
        'PYQ': 'Previous Year Questions (PYQ)',
        'MOCK': 'Mock Test',
    }
    return mapping.get(module, module)


def _sub_label_display(label: str) -> str:
    """Wrap sub-question label in parentheses if not already."""
    label = label.strip()
    if not label:
        return ''
    if label.startswith('(') and label.endswith(')'):
        return label
    return f'({label})'


def _render_shared_context_block(html: str) -> str:
    return f'<div class="shared-context-block">{html}</div>'


def _render_question_paper_html(
    groups: list,
    paper_title: str,
    subject_name: str,
    exam_level: str,
    module: str,
    total_marks: int,
    total_questions: int,
) -> str:
    """Build the full HTML string for the question paper."""
    gen_date = _safe_date()
    module_display = _module_display(module)

    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{paper_title}</title>
<style>
  body {{
    font-family: "Times New Roman", Times, serif;
    font-size: 12pt;
    margin: 2.5cm 2cm;
    color: #000;
    line-height: 1.5;
  }}
  .title-block {{
    text-align: center;
    margin-bottom: 1.5em;
  }}
  .title-block h1 {{
    font-size: 16pt;
    font-weight: bold;
    margin: 0 0 0.3em 0;
  }}
  .meta-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.2em 1em;
    font-size: 11pt;
    margin: 0.6em auto;
    max-width: 85%;
    text-align: left;
  }}
  .meta-grid .label {{ font-weight: bold; }}
  .divider {{
    border: none;
    border-top: 1.5px solid #000;
    margin: 1em 0;
  }}
  .instructions {{
    font-style: italic;
    font-size: 11pt;
    margin-bottom: 1.5em;
  }}
  /* Shared context block — shown once per group in question paper */
  .shared-context-block {{
    background: #f7f7f7;
    border-left: 3px solid #999;
    padding: 0.5em 0.8em;
    margin: 1em 0 0.5em 0;
    font-size: 11pt;
  }}
  .question-block {{
    margin: 1em 0;
    page-break-inside: avoid;
  }}
  .question-number {{
    font-weight: bold;
  }}
  .question-content {{
    margin-left: 1.5em;
  }}
  .sub-question {{
    margin: 0.4em 0 0.4em 1.5em;
  }}
  .sub-label {{
    font-weight: bold;
    display: inline-block;
    min-width: 2.5em;
  }}
  .marks {{
    float: right;
    font-weight: bold;
    font-size: 10pt;
    color: #333;
  }}
  .question-divider {{
    border: none;
    border-top: 0.5px solid #ccc;
    margin: 0.8em 0;
  }}
  /* ── Table styles ──────────────────────────────────────── */
  table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: auto;
    margin: 0.75em 0;
  }}
  th, td {{
    border: 1px solid #999;
    padding: 0.3em 0.6em;
    font-size: 10.5pt;
    vertical-align: top;
  }}
  th {{
    background: #EEEEEE;
    font-weight: bold;
  }}
  /* Prevent rows from splitting across page boundaries */
  tr {{
    page-break-inside: avoid;
  }}
  /* Repeat table header on each page */
  thead {{
    display: table-header-group;
  }}
  tfoot {{
    display: table-footer-group;
  }}
  /* Section rows — bold label spanning description column */
  tr.section-row td {{
    font-weight: bold;
    background: #F5F5F5;
  }}
  /* Total rows — bold with top border */
  tr.total-row td {{
    font-weight: bold;
    border-top: 2px solid #555;
  }}
  /* Images */
  img {{
    max-width: 100%;
    height: auto;
  }}
  p {{ margin: 0.3em 0; }}
</style>
</head>
<body>
<div class="title-block">
  <h1>{paper_title}</h1>
  <div class="meta-grid">
    <span class="label">Subject:</span><span>{subject_name}</span>
    <span class="label">Exam Level:</span><span>{exam_level}</span>
    <span class="label">Module:</span><span>{module_display}</span>
    <span class="label">Total Questions:</span><span>{total_questions}</span>
    <span class="label">Total Marks:</span><span>{total_marks}</span>
    <span class="label">Generated On:</span><span>{gen_date}</span>
  </div>
</div>
<hr class="divider">
<p class="instructions">Instructions: Answer all questions.</p>
<hr class="divider">
"""]

    previous_shared_context = None

    for i, group in enumerate(groups, start=1):
        # Deduplicate shared context — compare the full HTML string
        if group.shared_context_html != previous_shared_context:
            if group.shared_context_html:
                parts.append(_render_shared_context_block(group.shared_context_html))
            previous_shared_context = group.shared_context_html

        # Question block
        marks_tag = f'<span class="marks">[{group.total_marks} Marks]</span>' if group.total_marks else ''
        parts.append(f'<div class="question-block">')
        parts.append(f'<p class="question-number">{marks_tag}Question {i}.</p>')

        if group.sub_questions:
            parts.append(f'<div class="question-content">{group.question_html}</div>')
            for sq in group.sub_questions:
                label = _sub_label_display(sq.sub_question_label)
                sq_marks = f'<span class="marks">[{sq.marks} Marks]</span>' if sq.marks else ''
                parts.append(
                    f'<div class="sub-question">'
                    f'<span class="sub-label">{label}</span> {sq_marks}{sq.question_html}'
                    f'</div>'
                )
        else:
            parts.append(f'<div class="question-content">{group.question_html}</div>')

        parts.append('</div>')
        if i < len(groups):
            parts.append('<hr class="question-divider">')

    parts.append('</body></html>')
    return '\n'.join(parts)


def _render_answer_sheet_html(
    groups: list,
    paper_title: str,
    subject_name: str,
    exam_level: str,
    module: str,
) -> str:
    """Build the full HTML string for the answer sheet."""
    gen_date = _safe_date()
    module_display = _module_display(module)

    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{paper_title} — Suggested Answers</title>
<style>
  body {{
    font-family: "Times New Roman", Times, serif;
    font-size: 12pt;
    margin: 2.5cm 2cm;
    color: #000;
    line-height: 1.5;
  }}
  .title-block {{
    text-align: center;
    margin-bottom: 1.5em;
  }}
  .title-block h1 {{ font-size: 16pt; font-weight: bold; margin: 0 0 0.3em 0; }}
  .title-block h2 {{ font-size: 13pt; font-weight: normal; margin: 0; color: #444; }}
  .meta-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.2em 1em;
    font-size: 11pt;
    margin: 0.6em auto;
    max-width: 85%;
    text-align: left;
  }}
  .meta-grid .label {{ font-weight: bold; }}
  .divider {{ border: none; border-top: 1.5px solid #000; margin: 1em 0; }}
  .question-block {{ margin: 1em 0; page-break-inside: avoid; }}
  .question-number {{ font-weight: bold; }}
  .answer-label {{ font-weight: bold; font-size: 10pt; color: #555; margin: 0.3em 0; }}
  .answer-content {{ margin-left: 1.5em; }}
  .sub-question {{ margin: 0.6em 0 0.6em 1.5em; }}
  .sub-label {{ font-weight: bold; display: inline-block; min-width: 2.5em; }}
  .question-divider {{ border: none; border-top: 0.5px solid #ccc; margin: 0.8em 0; }}
  .working-notes {{ background: #f9f9f9; border: 1px solid #ddd; padding: 0.5em 0.8em; margin-top: 0.5em; font-size: 11pt; }}
  .working-notes h4 {{ margin: 0 0 0.3em 0; font-size: 11pt; }}
  /* ── Table styles ──────────────────────────────────────── */
  table {{ border-collapse: collapse; width: 100%; table-layout: auto; margin: 0.75em 0; }}
  th, td {{ border: 1px solid #999; padding: 0.3em 0.6em; font-size: 10.5pt; vertical-align: top; }}
  th {{ background: #EEEEEE; font-weight: bold; }}
  tr {{ page-break-inside: avoid; }}
  thead {{ display: table-header-group; }}
  tfoot {{ display: table-footer-group; }}
  tr.section-row td {{ font-weight: bold; background: #F5F5F5; }}
  tr.total-row td {{ font-weight: bold; border-top: 2px solid #555; }}
  img {{ max-width: 100%; height: auto; }}
  p {{ margin: 0.3em 0; }}
</style>
</head>
<body>
<div class="title-block">
  <h1>{paper_title}</h1>
  <h2>Suggested Answers</h2>
  <div class="meta-grid">
    <span class="label">Subject:</span><span>{subject_name}</span>
    <span class="label">Exam Level:</span><span>{exam_level}</span>
    <span class="label">Module:</span><span>{module_display}</span>
    <span class="label">Generated On:</span><span>{gen_date}</span>
  </div>
</div>
<hr class="divider">
"""]

    for i, group in enumerate(groups, start=1):
        # Shared context is NOT repeated in the answer sheet —
        # students refer back to the question paper for context.
        parts.append(f'<div class="question-block">')
        parts.append(f'<p class="question-number">Question {i}.</p>')

        if group.sub_questions:
            for sq in group.sub_questions:
                label = _sub_label_display(sq.sub_question_label)
                parts.append(
                    f'<div class="sub-question">'
                    f'<span class="sub-label">{label}</span>'
                    f'<div class="answer-label">Answer:</div>'
                    f'<div class="answer-content">{sq.answer_html}</div>'
                    f'</div>'
                )
        else:
            parts.append(
                f'<div class="answer-label">Answer:</div>'
                f'<div class="answer-content">{group.answer_html}</div>'
            )

        parts.append('</div>')
        if i < len(groups):
            parts.append('<hr class="question-divider">')

    parts.append('</body></html>')
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_question_paper(groups: list, paper_title: str) -> bytes:
    """
    Render a question paper PDF from fully-assembled QuestionGroup DTOs.

    Metadata (subject, exam level, module) is derived from groups[0].
    Shared contexts are deduplicated via a local tracking variable.
    Questions are renumbered 1, 2, 3... — original question_number not shown.
    Sub-question labels are preserved exactly from the database.

    Returns raw PDF bytes.
    """
    if not groups:
        raise ValueError("Cannot render a question paper with no groups.")

    first = groups[0]
    total_marks = sum(g.total_marks for g in groups)
    total_questions = len(groups)

    html_str = _render_question_paper_html(
        groups=groups,
        paper_title=paper_title,
        subject_name=first.subject_name,
        exam_level=first.exam_level,
        module=first.module,
        total_marks=total_marks,
        total_questions=total_questions,
    )

    logger.info(
        "Rendering question paper | title=%r | questions=%d | marks=%d",
        paper_title, total_questions, total_marks
    )
    return _html_to_pdf(html_str)


def render_answer_sheet(groups: list, paper_title: str) -> bytes:
    """
    Render a suggested answer sheet PDF from the same QuestionGroup DTOs.

    Must receive the same groups list (same order) as render_question_paper
    to guarantee question paper and answer sheet stay in sync.

    Shared context is NOT repeated in the answer sheet.
    Sub-question labels are preserved exactly from the database.

    Returns raw PDF bytes.
    """
    if not groups:
        raise ValueError("Cannot render an answer sheet with no groups.")

    first = groups[0]

    html_str = _render_answer_sheet_html(
        groups=groups,
        paper_title=paper_title,
        subject_name=first.subject_name,
        exam_level=first.exam_level,
        module=first.module,
    )

    logger.info(
        "Rendering answer sheet | title=%r | questions=%d",
        paper_title, len(groups)
    )
    return _html_to_pdf(html_str)
