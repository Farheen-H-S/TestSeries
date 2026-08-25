import os
import pymupdf as fitz
import re
from collections import Counter
from typing import List, Dict, Any, Set, Tuple

def detect_headers_footers(doc: fitz.Document) -> Set[str]:
    """
    Scans top and bottom margins of all pages to detect repeated running headers/footers.
    """
    margin_texts = Counter()
    total_pages = len(doc)
    
    for page in doc:
        blocks = page.get_text("blocks")
        rect = page.rect
        height = rect.height if rect else 842
        
        top_margin = 135
        bottom_margin = height - 135
        
        for b in blocks:
            x0, y0, x1, y1, text_val, block_no, block_type = b
            if y1 < top_margin or y0 > bottom_margin:
                clean_text = text_val.strip().lower()
                # Remove digits/page numbers to match core string
                clean_text = re.sub(r'\d+', '', clean_text).strip()
                if clean_text:
                    margin_texts[clean_text] += 1
                    
    # Repeated on > 30% of pages (or at least 3 pages)
    min_pages = max(3, int(total_pages * 0.3))
    return {text for text, count in margin_texts.items() if count >= min_pages}

PUA_SYMBOL_MAP = {
    "\uf073": "σ",
    "\uf062": "β",
    "\uf06d": "μ",
    "\uf072": "ρ",
    "\uf061": "α",
    "\uf064": "δ",
    "\uf044": "Δ",
    "\uf053": "Σ",
}

def normalize_text_glyphs(text: str) -> str:
    if not text:
        return ""
    for pua, char in PUA_SYMBOL_MAP.items():
        text = text.replace(pua, char)
    # Replace all backtick characters used as Indian Rupee symbols
    text = text.replace("`", "₹").replace("\u0060", "₹")
    return text

def is_near_table(bbox: Tuple[float, float, float, float], table_bboxes: List[Any], margin: float = 10.0) -> bool:
    bx0, by0, bx1, by1 = bbox
    cx = (bx0 + bx1) / 2
    cy = (by0 + by1) / 2
    for tx0, ty0, tx1, ty1 in table_bboxes:
        if (tx0 - margin <= cx <= tx1 + margin) and (ty0 - margin <= cy <= ty1 + margin):
            return True
    return False

def find_standalone_equation_regions(page: fitz.Page, table_bboxes: List[Any]) -> List[Tuple[float, float, float, float]]:
    """
    Detects bounding boxes of standalone mathematical formulas/equations outside of tables
    using horizontal fraction bar drawings, math glyph heuristics, and multi-line equation layout analysis.
    Captures full page width to guarantee no equations, labels, or side annotations are truncated.
    """
    raw_regions = []
    rect = getattr(page, 'rect', None)
    page_w = 595.0
    page_h = 842.0
    page_x0 = 0.0
    if rect and hasattr(rect, 'width'):
        try:
            page_w = float(rect.width)
            page_h = float(rect.height)
            page_x0 = float(rect.x0)
        except (TypeError, ValueError):
            page_w = 595.0
            page_h = 842.0
            page_x0 = 0.0
    
    top_margin_limit = max(145.0, page_h * 0.16)
    bottom_margin_limit = min(page_h - 145.0, page_h * 0.84)
    
    # 1. Detect from true fraction bar drawings
    drawings = []
    if hasattr(page, 'get_drawings'):
        try:
            res = page.get_drawings()
            if isinstance(res, list):
                drawings = res
        except Exception:
            pass
    for d in drawings:
        rect = d['rect']
        # Genuine fraction line: width >= 10pt, height <= 3.0pt, within body area and not near any table
        if rect.width >= 10 and rect.height <= 3.0 and top_margin_limit <= rect.y0 <= bottom_margin_limit:
            if not is_near_table(rect, table_bboxes, margin=8):
                # Ensure drawing is not part of a header banner
                is_header_meta = any(
                    re.search(r'(?i)\b(?:REVISION\s+TEST\s+PAPERS?|FINAL\s+EXAMINATION|DIRECT\s+TAX|FINANCIAL\s+MANAGEMENT|FINANCIAL\s+REPORTING|EXAMINATION)\b', s.get('text', ''))
                    for b in page.get_text('dict')['blocks'] if 'lines' in b
                    for l in b['lines'] for s in l['spans']
                    if rect.y0 - 25 <= s['bbox'][1] <= rect.y0 + 25
                )
                if is_header_meta:
                    continue

                # Ensure drawing is not a footnote separator line
                is_footnote = False
                if rect.y0 >= page_h * 0.80 or rect.x0 <= page_w * 0.20:
                    below_text = []
                    above_text = []
                    for b in page.get_text('dict')['blocks']:
                        if 'lines' in b:
                            for l in b['lines']:
                                for s in l['spans']:
                                    if rect.y1 <= s['bbox'][1] <= rect.y1 + 45:
                                        below_text.append(s['text'])
                                    if rect.y0 - 20 <= s['bbox'][3] <= rect.y0:
                                        above_text.append(s['text'])
                    bt = ' '.join(below_text)
                    at = ' '.join(above_text)
                    if any(k in bt for k in ['CIT', 'v.', 'ITR', 'Federal Bank', 'Rent received', 'Gross Annual Value', 'Municipal', '¹', '²', '³', '4', '5', 'High Court', 'Supreme Court', 'Notification', 'Circular']) or (rect.x0 <= page_w * 0.20 and not at):
                        is_footnote = True
                if is_footnote:
                    continue

                # Ensure drawing is a true mathematical fraction line, not an underline under normal prose text
                above_spans = []
                below_spans = []
                for b in page.get_text('dict')['blocks']:
                    if 'lines' in b:
                        for l in b['lines']:
                            for s in l['spans']:
                                sb = s['bbox']
                                if rect.y0 - 16 <= sb[3] <= rect.y0 + 2:
                                    above_spans.append(s['text'].strip())
                                if rect.y1 - 2 <= sb[1] <= rect.y1 + 16:
                                    below_spans.append(s['text'].strip())
                
                above_str = ' '.join([t for t in above_spans if t])
                below_str = ' '.join([t for t in below_spans if t])
                
                if not above_str or not below_str:
                    continue
                if re.search(r'(?i)\b(?:Reserves?|Surplus|Equity|Stock|Shares?|Capital|Particulars?|Total|Debit|Credit|Lakhs?|Crores?|Millions?|Billion)\b', above_str + ' ' + below_str):
                    continue
                
                has_math_sig = any(c in (above_str + ' ' + below_str) for c in ['=', '+', '-', '×', '/', '÷', '±', '∑', '√', '^', '%', 'σ', 'β', 'μ', 'ρ', 'λ', 'θ', 'XABC', 'Cov', 'Po', 'EPS', 'Ke', 'DPS', 'WACC', 'Rf', 'Rm', 'NPV', 'IRR'])
                has_digits = bool(re.search(r'\d', above_str) and re.search(r'\d', below_str))
                is_short_fraction = (len(above_str.split()) <= 4 and len(below_str.split()) <= 4)
                
                if not (has_math_sig or has_digits or is_short_fraction):
                    continue
                if len(above_str.split()) > 6 and not has_math_sig:
                    continue

                # Find all text spans on this page within y0 - 15 to y1 + 15
                line_spans = []
                for b in page.get_text('dict')['blocks']:
                    if 'lines' in b:
                        for l in b['lines']:
                            for s in l['spans']:
                                s_bbox = s['bbox']
                                if (rect.y0 - 15 <= s_bbox[1] <= rect.y1 + 15) or (rect.y0 - 15 <= s_bbox[3] <= rect.y1 + 15):
                                    line_spans.append(s_bbox)
                                    
                if line_spans:
                    min_y = max(0, min(s[1] for s in line_spans) - 4)
                    max_y = min(page_h, max(s[3] for s in line_spans) + 4)
                    raw_regions.append((page_x0, min_y, page_w, max_y))
                else:
                    raw_regions.append((
                        page_x0,
                        max(0, rect.y0 - 18),
                        page_w,
                        min(page_h, rect.y1 + 18)
                    ))

    # 2. Detect multi-line / complex math formula blocks (Greek symbols with powers, radicals, stacked lines)
    for b in page.get_text('dict')['blocks']:
        if 'lines' not in b:
            continue
        bbox = b['bbox']
        if bbox[1] < top_margin_limit or bbox[3] > bottom_margin_limit or is_near_table(bbox, table_bboxes, margin=8):
            continue
        lines = [''.join([s['text'] for s in l['spans']]).strip() for l in b['lines']]
        lines = [l for l in lines if l]
        text = ' '.join(lines)
        
        has_math_symbols = any(c in text for c in ['\uf073', 'σ', '\uf062', 'β', '\uf06d', 'μ', '\uf072', 'ρ', 'XABC', 'X_ABC', 'Cov.AX', 'Cov.', 'Po =', 'FCFE =', 'Ke =', 'EPS =', 'No. of Shares ='])
        
        height = bbox[3] - bbox[1]
        density = len(lines) / max(1, height)
        short_lines = [l for l in lines if len(l) <= 8]
        short_ratio = len(short_lines) / max(1, len(lines))
        
        is_formula_block = (
            (len(lines) >= 3 and density >= 0.25 and short_ratio >= 0.6) or
            (len(lines) >= 8 and density >= 0.30) or
            (has_math_symbols and ('=' in text or '(%)' in text or 'Cov' in text) and len(lines) >= 1)
        )
        if is_formula_block:
            if len(text.split()) > 15 and not ('=' in text and any(c in text for c in ['\uf073', 'σ', 'β', 'Po', 'EPS'])):
                continue
            raw_regions.append((
                page_x0,
                max(0, bbox[1] - 4),
                page_w,
                min(page_h, bbox[3] + 4)
            ))

    # 3. Detect Diagram / Flowchart / Schema clusters from vector drawings
    # If 3 or more drawings are clustered together within body area (e.g. flowcharts, organizational charts, accounting schema diagrams)
    diag_drawings = [
        d for d in drawings 
        if (d['rect'].height > 2 or d['rect'].width > 5) 
        and (top_margin_limit <= d['rect'].y0 and d['rect'].y1 <= bottom_margin_limit)
        and not is_near_table(d['rect'], table_bboxes, margin=8)
    ]
    
    clusters = []
    for d in diag_drawings:
        r = d['rect']
        merged_c = False
        for c in clusters:
            if not (r.y0 > c['max_y'] + 20 or r.y1 < c['min_y'] - 20):
                c['min_x'] = min(c['min_x'], r.x0)
                c['max_x'] = max(c['max_x'], r.x1)
                c['min_y'] = min(c['min_y'], r.y0)
                c['max_y'] = max(c['max_y'], r.y1)
                c['count'] += 1
                merged_c = True
                break
        if not merged_c:
            clusters.append({
                'min_x': r.x0,
                'max_x': r.x1,
                'min_y': r.y0,
                'max_y': r.y1,
                'count': 1
            })
            
    for c in clusters:
        if c['count'] >= 3:
            # Check if this cluster contains running header/footer banner text
            is_header_meta = False
            if hasattr(page, 'get_text'):
                try:
                    for b in page.get_text('dict')['blocks']:
                        if 'lines' in b:
                            for l in b['lines']:
                                for s in l['spans']:
                                    sy0, sy1 = s['bbox'][1], s['bbox'][3]
                                    if (c['min_y'] - 15 <= sy0 <= c['max_y'] + 15) or (c['min_y'] - 15 <= sy1 <= c['max_y'] + 15):
                                        if re.search(r'(?i)\b(?:REVISION\s+TEST\s+PAPERS?|MOCK\s+TEST|FINAL\s+EXAMINATION|INTERMEDIATE\s+EXAMINATION|FOUNDATION|EXAMINATION|MAY\s+20\d\d|NOV\s+20\d\d|SEPT\s+20\d\d|JAN\s+20\d\d)\b', s.get('text', '')):
                                            is_header_meta = True
                                            break
                except Exception:
                    pass
            if is_header_meta:
                continue

            d_min_y = c['min_y']
            d_max_y = c['max_y']
            if hasattr(page, 'get_text'):
                try:
                    for b in page.get_text('dict')['blocks']:
                        if 'lines' in b:
                            for l in b['lines']:
                                for s in l['spans']:
                                    sx0, sy0, sx1, sy1 = s['bbox']
                                    if (c['min_x'] - 10 <= sx0 and sx1 <= c['max_x'] + 10) and (c['min_y'] - 4 <= sy0 <= c['max_y'] + 4):
                                        d_min_y = min(d_min_y, sy0)
                                        d_max_y = max(d_max_y, sy1)
                except Exception:
                    pass
            raw_regions.append((
                page_x0,
                max(0, d_min_y - 3),
                page_w,
                min(page_h, d_max_y + 3)
            ))

    if not raw_regions:
        return []
        
    merged = []
    for r in sorted(raw_regions, key=lambda x: (x[1], x[0])):
        if not merged:
            merged.append(list(r))
        else:
            prev = merged[-1]
            has_header_between = False
            if hasattr(page, 'get_text'):
                for b in page.get_text('blocks'):
                    if (prev[1] - 2.0 <= b[1] <= r[3] + 2.0):
                        b_text = b[4].strip()
                        if re.search(r'(?i)(?:^|\n)\s*(?:[1-9]\d?\.|\([a-z]\)|\([ivx]+\))\s+[A-Za-z]', b_text):
                            has_header_between = True
                            break
            v_overlap = (r[1] <= prev[3] + 8) and (r[3] >= prev[1] - 8) and not has_header_between
            if v_overlap:
                prev[0] = min(prev[0], r[0])
                prev[1] = min(prev[1], r[1])
                prev[2] = max(prev[2], r[2])
                prev[3] = max(prev[3], r[3])
            else:
                merged.append(list(r))
                
    final_regions = []
    for r in merged:
        final_regions.append((
            page_x0,
            max(0.0, r[1] - 4),
            page_w,
            min(page_h, r[3] + 4)
        ))
    return final_regions

def extract_text(doc: fitz.Document, document_id: Any = None) -> List[Dict[str, Any]]:
    """
    Extract raw text from a PDF document page-by-page.
    Detects tables and complex equations and replaces them with visual crop blocks.
    Strips running page headers and footers from margins.
    """
    from .table_processing import TableProcessor
    
    repeated_margin_texts = detect_headers_footers(doc)
    extracted_pages = []

    # Pass 1: Extract all tables across all pages, process, and merge them
    processor = TableProcessor()
    table_lookup = processor.process_document(doc, document_id=document_id)

    # Pass 2: Extract text page by page, integrating processed table and equation visual blocks
    for page in doc:
        page_num = page.number + 1
        rect = page.rect
        height = rect.height if rect else 842
        top_margin = 135
        bottom_margin = height - 135
        
        page_tables = page.find_tables().tables
        blocks = page.get_text("blocks")
        items = []
        from .table_processing import is_mcq_answer_key_table
        valid_page_tables = [t for t in page_tables if (page_num, round(t.bbox[0], 1), round(t.bbox[1], 1)) in table_lookup]
        table_bboxes = [t.bbox for t in valid_page_tables]
        all_table_bboxes = [t.bbox for t in valid_page_tables]
        
        # Add tables and extract effective visual region bboxes
        for t in valid_page_tables:
            key = (page_num, round(t.bbox[0], 1), round(t.bbox[1], 1))
            md_content = table_lookup.get(key, "")
            is_mcq = is_mcq_answer_key_table(t.extract())
            if md_content:
                if is_mcq:
                    items.append({
                        "type": "text",
                        "y0": t.bbox[1],
                        "x0": t.bbox[0],
                        "content": md_content
                    })
                else:
                    items.append({
                        "type": "table",
                        "y0": t.bbox[1],
                        "x0": t.bbox[0],
                        "content": md_content
                    })
                    m_prov = re.search(r'data-table-provenance="([^"]+)"', md_content)
                    added_prov = False
                    if m_prov:
                        try:
                            import json, html as html_lib
                            prov_dict = json.loads(html_lib.unescape(m_prov.group(1)))
                            for r_item in prov_dict.get("regions", []):
                                if r_item.get("page_number") == page_num and r_item.get("bbox") and len(r_item["bbox"]) == 4:
                                    table_bboxes.append(tuple(r_item["bbox"]))
                                    added_prov = True
                        except Exception:
                            pass
                    if not added_prov:
                        table_bboxes.append(t.bbox)

        # Add standalone formula / equation visual crops
        formula_regions = find_standalone_equation_regions(page, all_table_bboxes)
        for f_idx, f_box in enumerate(formula_regions):
            doc_prefix = f"doc{document_id}" if document_id else "doc"
            crop_filename = f"{doc_prefix}_p{page_num}_formula_y{int(f_box[1])}.png"
            
            try:
                from django.conf import settings
                media_root = getattr(settings, "MEDIA_ROOT", None)
                if not media_root:
                    media_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "media"))
            except Exception:
                media_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "media"))
            crops_dir = os.path.join(str(media_root), "formula_crops")
            os.makedirs(crops_dir, exist_ok=True)
            crop_path = os.path.join(crops_dir, crop_filename)
            
            f_rect = fitz.Rect(
                float(page.rect.x0 if page.rect else 0.0),
                max(0.0, float(f_box[1] - 4)),
                float(page.rect.width if page.rect else 595.0),
                min(float(page.rect.height if page.rect else 842.0), float(f_box[3] + 4))
            )
            pix = page.get_pixmap(matrix=fitz.Matrix(200/72, 200/72), clip=f_rect)
            pix.save(crop_path)
            
            crop_rel_path = f"/media/formula_crops/{crop_filename}"
            html_rep = (
                f'<div class="formula-container" data-is-complex="true" data-crop-path="{crop_rel_path}">'
                f'<div class="formula-visual-region" style="text-align:center; margin: 0.5em 0;">'
                f'<img src="{crop_rel_path}" style="max-width: 100%; height: auto; display: block; margin: 0.5em auto;" />'
                f'</div></div>'
            )
            items.append({
                "type": "formula",
                "y0": f_box[1],
                "x0": f_box[0],
                "content": html_rep
            })
            
        # Add text blocks that do not fall inside any table or formula bbox and are not margin headers/footers
        page_left_margin_threshold = (page.rect.width * 0.30) if page.rect else 160.0
        for b in blocks:
            bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
            text_val = b[4]
            
            # Check if block falls in page margin (running header/footer check)
            if by1 < top_margin or by0 > bottom_margin:
                clean_text = text_val.strip().lower()
                clean_text = re.sub(r'\d+', '', clean_text).strip()
                # If block text matches repeated margins, or is purely numeric (page number)
                if not clean_text or clean_text in repeated_margin_texts:
                    continue
            
            cx = (bx0 + bx1) / 2
            cy = (by0 + by1) / 2
            
            # 1. Blocks inside tables are ALWAYS suppressed because tables are extracted/serialized by table_lookup
            inside_table = False
            for tx0, ty0, tx1, ty1 in table_bboxes:
                if (tx0 - 4.0 <= cx <= tx1 + 4.0) and (ty0 - 2.0 <= cy <= ty1 + 2.0):
                    inside_table = True
                    break

            if inside_table:
                continue

            # 2. Blocks inside formula crops are suppressed UNLESS they start with a question/subquestion header
            is_question_header_block = False
            b_first_line = text_val.strip().split('\n')[0].strip()
            if re.match(r'^(?:Question\s+(?:No\.\s*)?\d+|Q\.?\s*\d+|\d{1,2}\.\s+[A-Za-z]|\d{1,2}\.\s*\([a-zA-ZivxIVX]+\)|\d{1,2}\s*\([a-zA-ZivxIVX]+\)|\([a-zA-ZivxIVX]+\)\s+[A-Za-z])', b_first_line):
                is_question_header_block = True

            inside_formula = False
            if not is_question_header_block:
                for fx0, fy0, fx1, fy1 in formula_regions:
                    if (fx0 - 4.0 <= cx <= fx1 + 4.0) and (fy0 - 2.0 <= cy <= fy1 + 2.0):
                        inside_formula = True
                        break

            if not inside_formula:
                items.append({
                    "type": "text",
                    "y0": by0,
                    "x0": bx0,
                    "content": normalize_text_glyphs(text_val)
                })
                
        # Sort items primarily by y0 (vertical), then by x0 (horizontal)
        items.sort(key=lambda x: (x["y0"], x["x0"]))
        
        # Reconstruct page text
        page_text_parts = []
        for it in items:
            if it["type"] in ("table", "formula"):
                if it["content"].strip():
                    page_text_parts.append(f"\n[STRUCTURED_START]\n{it['content']}\n[STRUCTURED_END]\n")
            else:
                page_text_parts.append(it["content"])
                
        page_text = "\n".join(page_text_parts)
        
        page_content = {
            "page_number": page_num,
            "text": page_text
        }
        extracted_pages.append(page_content)

    return extracted_pages


