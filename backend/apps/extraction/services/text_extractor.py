import os
import fitz
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
    """
    raw_regions = []
    
    # 1. Detect from true fraction bar drawings
    drawings = page.get_drawings()
    for d in drawings:
        rect = d['rect']
        # Genuine fraction line: width between 12 and 180pt, height <= 2.5pt, strictly within body area (155-695pt) and not near any table
        if 12 <= rect.width <= 180 and rect.height <= 2.5 and 155 <= rect.y0 <= 695:
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
                    min_x = max(132.0, min(s[0] for s in line_spans) - 5)
                    max_x = min(page.rect.width, max(s[2] for s in line_spans) + 8)
                    min_y = max(0, min(s[1] for s in line_spans) - 4)
                    max_y = min(page.rect.height, max(s[3] for s in line_spans) + 4)
                    raw_regions.append((min_x, min_y, max_x, max_y))
                else:
                    raw_regions.append((
                        max(132.0, rect.x0 - 45),
                        max(0, rect.y0 - 18),
                        min(page.rect.width, rect.x1 + 25),
                        min(page.rect.height, rect.y1 + 18)
                    ))

    # 2. Detect multi-line / complex math formula blocks (Greek symbols with powers, radicals, stacked lines)
    for b in page.get_text('dict')['blocks']:
        if 'lines' not in b:
            continue
        bbox = b['bbox']
        if bbox[1] < 140 or bbox[3] > 710 or is_near_table(bbox, table_bboxes, margin=8):
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
                max(132.0, bbox[0] - 5),
                max(0, bbox[1] - 3),
                min(page.rect.width, bbox[2] + 8),
                min(page.rect.height, bbox[3] + 3)
            ))

    if not raw_regions:
        return []
        
    merged = []
    for r in sorted(raw_regions, key=lambda x: (x[1], x[0])):
        if not merged:
            merged.append(list(r))
        else:
            prev = merged[-1]
            v_overlap = (r[1] <= prev[3] + 12) and (r[3] >= prev[1] - 12)
            h_overlap = not (r[2] < prev[0] - 25 or r[0] > prev[2] + 25)
            if v_overlap and h_overlap:
                prev[0] = min(prev[0], r[0])
                prev[1] = min(prev[1], r[1])
                prev[2] = max(prev[2], r[2])
                prev[3] = max(prev[3], r[3])
            else:
                merged.append(list(r))
                
    final_regions = []
    for r in merged:
        final_regions.append((
            max(132.0, r[0] - 3),
            max(0, r[1] - 3),
            min(page.rect.width, r[2] + 5),
            min(page.rect.height, r[3] + 3)
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
        valid_page_tables = [t for t in page_tables if (page_num, round(t.bbox[0], 1), round(t.bbox[1], 1)) in table_lookup]
        table_bboxes = [t.bbox for t in valid_page_tables]
        
        # Add tables
        for t in valid_page_tables:
            key = (page_num, round(t.bbox[0], 1), round(t.bbox[1], 1))
            md_content = table_lookup.get(key, "")
            items.append({
                "type": "table",
                "y0": t.bbox[1],
                "x0": t.bbox[0],
                "content": md_content
            })

        # Add standalone formula / equation visual crops
        formula_regions = find_standalone_equation_regions(page, table_bboxes)
        for f_idx, f_box in enumerate(formula_regions):
            doc_prefix = f"doc{document_id}" if document_id else "doc"
            crop_filename = f"{doc_prefix}_p{page_num}_formula_y{int(f_box[1])}.png"
            
            try:
                from django.conf import settings
                media_root = getattr(settings, "MEDIA_ROOT", "media")
            except Exception:
                media_root = "media"
            crops_dir = os.path.join(media_root, "formula_crops")
            os.makedirs(crops_dir, exist_ok=True)
            crop_path = os.path.join(crops_dir, crop_filename)
            
            f_rect = fitz.Rect(f_box)
            pix = page.get_pixmap(matrix=fitz.Matrix(200/72, 200/72), clip=f_rect)
            pix.save(crop_path)
            
            disp_width = int(f_box[2] - f_box[0])
            crop_rel_path = f"/media/formula_crops/{crop_filename}"
            html_rep = (
                f'<div class="formula-container" data-is-complex="true" data-crop-path="{crop_rel_path}">'
                f'<div class="formula-visual-region" style="text-align:center; margin: 0.5em 0;">'
                f'<img src="{crop_rel_path}" style="max-width: 100%; width: {disp_width}px; height: auto; display: inline-block;" />'
                f'</div></div>'
            )
            items.append({
                "type": "formula",
                "y0": f_box[1],
                "x0": f_box[0],
                "content": html_rep
            })
            
        # Add text blocks that do not fall inside any table or formula bbox and are not margin headers/footers
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
            
            inside_visual = False
            for tx0, ty0, tx1, ty1 in table_bboxes + formula_regions:
                if (tx0 <= cx <= tx1) and (ty0 <= cy <= ty1):
                    inside_visual = True
                    break

            if inside_visual:
                # If block starts in left margin (x0 < 132) and contains a question/answer header, preserve the header text!
                m_hdr = re.match(r'^\s*(\d+\.|\([a-z]\)|\([ivx\d]+\))\s*', text_val, re.IGNORECASE)
                if m_hdr and bx0 < 132:
                    hdr_text = m_hdr.group(1)
                    items.append({
                        "type": "text",
                        "y0": by0,
                        "x0": bx0,
                        "content": hdr_text
                    })
            else:
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


