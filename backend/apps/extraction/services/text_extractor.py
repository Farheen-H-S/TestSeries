import fitz
import re
from collections import Counter
from typing import List, Dict, Any, Set

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

def extract_text(doc: fitz.Document) -> List[Dict[str, Any]]:
    """
    Extract raw text from a PDF document page-by-page.
    Detects tables and replaces them with wrapped markdown blocks.
    Strips running page headers and footers from margins.
    """
    repeated_margin_texts = detect_headers_footers(doc)
    extracted_pages = []

    for page in doc:
        rect = page.rect
        height = rect.height if rect else 842
        top_margin = 135
        bottom_margin = height - 135
        
        tables = page.find_tables().tables
        blocks = page.get_text("blocks")
        
        # Segment page blocks and tables together by vertical position
        items = []
        table_bboxes = [t.bbox for t in tables]
        
        # Add tables
        for t in tables:
            items.append({
                "type": "table",
                "y0": t.bbox[1],
                "x0": t.bbox[0],
                "content": t.to_markdown()
            })
            
        # Add text blocks that do not fall inside any table bbox and are not margin headers/footers
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
            
            # Check center of text block to see if it is inside any table
            cx = (bx0 + bx1) / 2
            cy = (by0 + by1) / 2
            
            inside_table = False
            for tx0, ty0, tx1, ty1 in table_bboxes:
                if (tx0 <= cx <= tx1) and (ty0 <= cy <= ty1):
                    inside_table = True
                    break
                    
            if not inside_table:
                items.append({
                    "type": "text",
                    "y0": by0,
                    "x0": bx0,
                    "content": text_val
                })
                
        # Sort items primarily by y0 (vertical), then by x0 (horizontal)
        items.sort(key=lambda x: (x["y0"], x["x0"]))
        
        # Reconstruct page text
        page_text_parts = []
        for it in items:
            if it["type"] == "table":
                page_text_parts.append(f"\n[STRUCTURED_START]\n{it['content']}\n[STRUCTURED_END]\n")
            else:
                page_text_parts.append(it["content"])
                
        page_text = "\n".join(page_text_parts)
        
        page_content = {
            "page_number": page.number + 1,
            "text": page_text
        }
        extracted_pages.append(page_content)

    return extracted_pages


