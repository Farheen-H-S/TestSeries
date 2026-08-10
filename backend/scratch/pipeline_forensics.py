"""Pipeline Forensics: Trace a representative broken table across all 6 pipeline stages."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TestSeries.settings')
import django
django.setup()

from apps.papers.models import Question
from apps.papers.services.question_selector import build_group
from apps.papers.services.pdf_renderer import _render_answer_sheet_html
from apps.extraction.services.html_formatter import clean_stored_html_tables, sanitize_stored_html_table
from bs4 import BeautifulSoup
import fitz

def run_forensics():
    report = []
    report.append("================================================================================")
    report.append("PIPELINE FORENSICS: REPRESENTATIVE BROKEN TABLE DIAGNOSTIC REPORT")
    report.append("================================================================================")

    # Find Question 6 (Question ID 1706) from Document 38
    q = Question.objects.filter(question_number='6').first()
    if not q:
        q = Question.objects.filter(answer_content__icontains='<table').first()

    report.append(f"Target Question: ID {q.question_id}, Num {q.question_number}, Doc ID {q.document_id}")
    report.append("")

    # --- STAGE 1: Raw DB answer_content ---
    report.append("--- STAGE 1: RAW DB answer_content ---")
    raw_ac = q.answer_content or ""
    report.append(f"Raw answer_content length: {len(raw_ac)} chars")
    soup_stage1 = BeautifulSoup(raw_ac, 'html.parser')
    tables_stage1 = soup_stage1.find_all('table')
    report.append(f"Found {len(tables_stage1)} tables in raw DB answer_content.")
    if tables_stage1:
        target_t = tables_stage1[0]
        report.append("\n[Stage 1 Raw Table 0 HTML]:")
        report.append(target_t.prettify()[:1500])

    # --- STAGE 2: BeautifulSoup parsed container ---
    report.append("\n--- STAGE 2: BEAUTIFULSOUP PARSED CONTAINER ---")
    containers = soup_stage1.find_all('div', class_='table-container')
    if not containers:
        containers = soup_stage1.find_all('table')
    report.append(f"Found {len(containers)} containers.")
    if containers:
        c0 = containers[0]
        report.append("\n[Stage 2 Container 0 HTML]:")
        report.append(c0.prettify()[:1500])

    # --- STAGE 3: sanitize_stored_html_table output ---
    report.append("\n--- STAGE 3: SANITIZED TABLE OUTPUT ---")
    if containers:
        stage3_html = sanitize_stored_html_table(c0)
        report.append("\n[Stage 3 Sanitized HTML]:")
        report.append(stage3_html[:1500])

    # --- STAGE 4: _prerender_html_content output ---
    report.append("\n--- STAGE 4: _prerender_html_content OUTPUT ---")
    stage4_html = clean_stored_html_tables(raw_ac)
    report.append("\n[Stage 4 Cleaned HTML]:")
    report.append(stage4_html[:1500])

    # --- STAGE 5: Final HTML fed into PDF Renderer (_render_answer_sheet_html) ---
    report.append("\n--- STAGE 5: FINAL HTML INPUT TO PDF RENDERER ---")
    group = build_group(q)
    final_pdf_input_html = _render_answer_sheet_html([group], "Diagnostic Paper", "Financial Reporting", "Final", "RTP")
    report.append("\n[Stage 5 Final Input HTML to xhtml2pdf]:")
    soup_stage5 = BeautifulSoup(final_pdf_input_html, 'html.parser')
    t_stage5 = soup_stage5.find('table')
    if t_stage5:
        report.append(t_stage5.prettify()[:1500])
    else:
        report.append(final_pdf_input_html[:1500])

    # --- STAGE 6: Rendered PDF Output via xhtml2pdf ---
    report.append("\n--- STAGE 6: RENDERED PDF PAGE TEXT & BOUNDING BOX ANALYSIS ---")
    from xhtml2pdf import pisa
    import io
    pdf_out = io.BytesIO()
    pisa.CreatePDF(final_pdf_input_html, dest=pdf_out)
    pdf_bytes = pdf_out.getvalue()
    report.append(f"Rendered PDF size: {len(pdf_bytes)} bytes.")

    doc = fitz.open("pdf", pdf_bytes)
    report.append(f"Rendered PDF pages: {len(doc)}")
    for i, page in enumerate(doc):
        report.append(f"\n--- Page {i} Text ---")
        text = page.get_text()
        report.append(text[:800])

    # Write report to file
    report_str = "\n".join(report)
    print(report_str)
    
    with open("pipeline_forensics_report.txt", "w", encoding="utf-8") as f:
        f.write(report_str)

if __name__ == '__main__':
    run_forensics()
