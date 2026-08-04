import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from apps.extraction.services.pdf_loader import load_pdf
from apps.extraction.services.text_extractor import extract_text
from apps.extraction.services.normalizer import Normalizer
from apps.extraction.services.extraction_patterns import get_default_parser_config
from apps.extraction.services.layout_detector import DocumentLayoutDetector
from apps.extraction.services.section_splitter import SectionSplitter
from apps.extraction.services.types import LayoutType
from apps.extraction.services.answer_parser import AnswerParser

pdf_path = r"d:\Farheen\TestSeries\backend\media\documents\rtp-may-2026-fr.pdf"
doc = load_pdf(pdf_path)
pages_data = extract_text(doc)
doc.close()

full_text = ""
for p in pages_data:
    full_text += p["text"] + "\n"

normalized_full_text = Normalizer.pre_normalize_ocr(full_text)
config = get_default_parser_config()
detector = DocumentLayoutDetector(config)
layout_res = detector.detect_layout(normalized_full_text)

splitter = SectionSplitter()
if layout_res.layout != LayoutType.UNKNOWN:
    q_part, a_part = splitter.split(full_text, layout_res.boundary_position)
    a_base_offset = layout_res.boundary_position
else:
    q_part, a_part = full_text, full_text
    a_base_offset = 0

page_offsets = []
current_offset = 0
for p in pages_data:
    page_offsets.append((current_offset, p["page_number"]))
    current_offset += len(p["text"]) + 1

# Mock parsed question paths (from actual QuestionParser output on rtp-may-2026-fr.pdf)
mock_question_paths = {
    ('8',), ('8', 'i'), ('8', 'ii'),
    ('10',),
    ('11',),
    ('12',), ('12', 'i'), ('12', 'ii')
}

a_parser = AnswerParser(config)

print("\n=== Parsing with REAL AnswerParser (with valid_question_paths) ===")
answers_with_paths = a_parser.parse(
    a_part,
    page_offsets,
    base_offset=a_base_offset,
    valid_question_paths=mock_question_paths
)

print("\n--- Parsed Answer Paths ---")
for ans in answers_with_paths:
    c_main = ans.hierarchy_path[0] if ans.hierarchy_path else None
    if c_main in ('7', '8', '9', '10', '11', '12'):
        print(f"Header: {repr(ans.raw_header)} | Path: {ans.hierarchy_path} | Length: {len(ans.text)}")

print("\n=== Parsing with REAL AnswerParser (fallback - no question paths) ===")
answers_fallback = a_parser.parse(
    a_part,
    page_offsets,
    base_offset=a_base_offset,
    valid_question_paths=None
)

print("\n--- Fallback Parsed Answer Paths ---")
for ans in answers_fallback:
    c_main = ans.hierarchy_path[0] if ans.hierarchy_path else None
    if c_main in ('7', '8', '9', '10', '11', '12'):
        print(f"Header: {repr(ans.raw_header)} | Path: {ans.hierarchy_path} | Length: {len(ans.text)}")
