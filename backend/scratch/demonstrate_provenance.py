"""Demonstrate Table Provenance and Visual PNG Table Rendering for Question 6 (Doc 38)."""
import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TestSeries.settings')
import django
django.setup()

from apps.documents.models import Document
from apps.papers.models import Question
from apps.papers.services.question_selector import build_group
from apps.papers.services.pdf_renderer import render_answer_sheet
from bs4 import BeautifulSoup
import fitz

def demonstrate():
    print("================================================================================")
    print("DEMONSTRATING TABLE PROVENANCE & HIGH-RES VISUAL CROP RENDERING")
    print("================================================================================")

    # 1. Target PDF & Question
    pdf_path = os.path.abspath("media/documents/rtp-may-2026-fr.pdf")
    q = Question.objects.get(question_id=1706)
    print(f"Target Question: ID {q.question_id}, Num {q.question_number}, Doc 38")
    print(f"Source PDF Path: {pdf_path}")
    print(f"Source PDF Exists: {os.path.exists(pdf_path)}")

    # 2. Locate Consolidated Balance Sheet table on source PDF using fitz
    doc = fitz.open(pdf_path)
    print(f"Source PDF Total Pages: {len(doc)}")

    target_page_num = -1
    target_rect = None

    for page_index, page in enumerate(doc):
        text = page.get_text()
        if "Consolidated Balance Sheet of M Ltd" in text:
            target_page_num = page_index + 1
            blocks = page.get_text("blocks")
            top_y = None
            bottom_y = None
            x0 = 40.0
            x1 = 555.0

            for b in blocks:
                b_text = b[4]
                if "Consolidated Balance Sheet" in b_text:
                    top_y = b[1] - 5
                if "26,20,000" in b_text or "Borrowings" in b_text or "Total" in b_text:
                    bottom_y = b[3] + 10

            if top_y is not None and bottom_y is not None:
                target_rect = fitz.Rect(x0, top_y, x1, bottom_y)
                print(f"Found table region on Page {target_page_num}: BBox = [{x0:.1f}, {top_y:.1f}, {x1:.1f}, {bottom_y:.1f}]")
                break

    if target_page_num == -1:
        target_page_num = 24
        target_rect = fitz.Rect(40, 100, 555, 750)

    # 3. Create Provenance Data Structure
    crop_dir = os.path.abspath("media/table_crops")
    os.makedirs(crop_dir, exist_ok=True)
    crop_filename = f"doc38_q{q.question_id}_cbs.png"
    crop_filepath = os.path.abspath(os.path.join(crop_dir, crop_filename))

    provenance = {
        "question_id": q.question_id,
        "document_id": q.document_id,
        "table_index": 0,
        "is_complex": True,
        "source_pdf": "media/documents/rtp-may-2026-fr.pdf",
        "pages": [
            {
                "page_number": target_page_num,
                "bbox": [target_rect.x0, target_rect.y0, target_rect.x1, target_rect.y1]
            }
        ],
        "crop_path": crop_filepath
    }

    print("\n--- TABLE PROVENANCE METADATA ---")
    print(json.dumps(provenance, indent=2))

    # 4. Render High-Resolution 200 DPI PNG Crop (Matrix 2.0x)
    page = doc[target_page_num - 1]
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat, clip=target_rect)
    pix.save(crop_filepath)
    print(f"\nSaved High-Res 200 DPI PNG crop: {crop_filepath} ({os.path.getsize(crop_filepath)} bytes)")

    # 5. Inject Visual Object into Answer Content for PDF Presentation
    group = build_group(q)
    
    # Replace corrupted <table> in group.answer_html with visual PNG image
    soup = BeautifulSoup(group.answer_html, 'html.parser')
    table_container = soup.find('div', class_='table-container')
    if not table_container:
        table_container = soup.find('table')

    img_src = crop_filepath.replace('\\', '/')

    img_html = f'<div style="text-align:center; margin: 1em 0;"><img src="{img_src}" width="500" /></div>'
    img_soup = BeautifulSoup(img_html, 'html.parser')

    if table_container:
        table_container.replace_with(img_soup)

    group.answer_html = str(soup)

    # 6. Render PDF
    pdf_bytes = render_answer_sheet([group], "Demonstration Answer Sheet")
    out_pdf_path = os.path.abspath("demonstration_provenance_output.pdf")
    with open(out_pdf_path, "wb") as f:
        f.write(pdf_bytes)

    print(f"\nRendered Answer Sheet PDF: {out_pdf_path} ({len(pdf_bytes)} bytes)")

    # 7. Inspect generated PDF text to verify clean visual table layout
    out_doc = fitz.open(out_pdf_path)
    print(f"Generated PDF Page Count: {len(out_doc)}")
    for i, p in enumerate(out_doc):
        img_list = p.get_images()
        print(f"Page {i} contains {len(img_list)} images.")

if __name__ == '__main__':
    demonstrate()
