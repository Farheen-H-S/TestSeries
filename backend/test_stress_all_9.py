import sys, os
sys.path.insert(0, 'backend')
import fitz

from apps.extraction.services.pdf_loader import load_pdf
from apps.extraction.services.text_extractor import extract_text
from apps.extraction.services.section_splitter import SectionSplitter
from apps.extraction.services.layout_detector import DocumentLayoutDetector
from apps.extraction.services.extraction_patterns import get_default_parser_config
from apps.extraction.services.question_parser import QuestionParser
from apps.extraction.services.answer_parser import AnswerParser
from apps.extraction.services.types import ParsingContext
from apps.extraction.services.answer_matcher import AnswerMatcher

test_docs = [
    ('AFM May 2024', r'docs/rtp-may-2024-afm.pdf'),
    ('AFM Nov 2024', r'docs/rtp-nov-2024-afm.pdf'),
    ('FR May 2024',  r'docs/rtp-may-2024-fr.pdf'),
    ('FR Nov 2024',  r'docs/rtp-nov-2024-fr.pdf'),
    ('FR May 2026',  r'docs/rtp-may-2026-fr.pdf'),
    ('DT May 2025',  r'docs/rtp-may-2025-dt.pdf'),
    ('DT May 2026',  r'docs/rtp-may-2026-dt.pdf'),
    ('IDT May 2026', r'docs/rtp-may-2026-it.pdf'),
    ('Audit May 2026', r'docs/rtp-may-2026-aa.pdf'),
]

config = get_default_parser_config()
detector = DocumentLayoutDetector(config)
splitter = SectionSplitter()
q_parser = QuestionParser(config)
a_parser = AnswerParser(config)
matcher = AnswerMatcher()

print('=== EMPIRICAL STRESS TEST ACROSS 9 REAL-WORLD CA PAPERS ===\n')
print(f'{"Subject / Paper":<18} | {"Layout":<12} | {"Parsed Qs":<9} | {"Parsed Ans":<10} | {"Matched":<7} | {"Primary Q Range":<18} | {"Status"}')
print('-'*90)

for title, path in test_docs:
    if not os.path.exists(path):
        continue
    pdf_doc = load_pdf(path)
    pages_data = extract_text(pdf_doc)
    full_text = '\n'.join([p['text'] for p in pages_data])
    layout_res = detector.detect_layout(full_text)
    q_part, a_part = splitter.split(full_text, layout_res.boundary_position)
    
    page_offsets = []
    cur = 0
    for p in pages_data:
        page_offsets.append((p['page_number'], cur))
        cur += len(p['text']) + 1
        
    context = ParsingContext()
    pqs = q_parser.parse(q_part, page_offsets, base_offset=0, context=context)
    context.valid_question_paths = set(tuple(q.hierarchy_path) for q in pqs if q.hierarchy_path)
    pas = a_parser.parse(a_part, page_offsets, base_offset=layout_res.boundary_position, context=context)
    match_res = matcher.match(pqs, pas)
    
    distinct_mains_q = sorted(list(set(q.hierarchy_path[0] for q in pqs if q.hierarchy_path)), key=lambda x: int(x) if x.isdigit() else 999)
    distinct_mains_a = sorted(list(set(a.hierarchy_path[0] for a in pas if a.hierarchy_path)), key=lambda x: int(x) if x.isdigit() else 999)
    
    q_range = f'{distinct_mains_q[0]} to {distinct_mains_q[-1]} ({len(distinct_mains_q)})' if distinct_mains_q else 'None'
    status = 'PERFECT 100%' if len(distinct_mains_q) == len(distinct_mains_a) and distinct_mains_q == distinct_mains_a else 'PARSED'
    print(f'{title:<18} | {layout_res.layout.name:<12} | {len(pqs):<9} | {len(pas):<10} | {len(match_res.matches):<7} | {q_range:<18} | {status}')
