import html
import re
from typing import Optional
from .table_processing import parse_markdown_to_table, TableProcessor

def escape_html(text: str) -> str:
    """
    Escape special characters to be HTML-safe.
    """
    return html.escape(text)

def preserve_paragraphs(text: str) -> str:
    """
    Convert double newlines into simple HTML paragraphs and replace single newlines with br tags.
    """
    if not text.strip():
        return ""
    
    # Split by double or more newlines to identify paragraphs, handling spaces
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    
    # Wrap each paragraph in <p> tags and convert internal newlines to <br />
    html_paragraphs = []
    for p in paragraphs:
        p_formatted = p.replace('\n', '<br />')
        html_paragraphs.append(f"<p>{p_formatted}</p>")
        
    return "\n".join(html_paragraphs)

def markdown_table_to_html(markdown_table: str) -> str:
    """
    Parses a simple markdown table into a semantic HTML table with thead and tbody.
    """
    table = parse_markdown_to_table(markdown_table)
    return TableProcessor.render_to_html(table)

def text_to_html(text: str) -> str:
    """
    Convert plain text to HTML. Converts structured markdown tables and escapes normal text safely,
    ensuring tables are not nested inside paragraphs.
    """
    if not text:
        return ""
        
    # Split by structured table blocks
    parts = re.split(r"(\[STRUCTURED_START\].*?\[STRUCTURED_END\])", text, flags=re.DOTALL)
    html_parts = []
    
    for part in parts:
        if not part:
            continue
            
        if part.startswith("[STRUCTURED_START]") and part.endswith("[STRUCTURED_END]"):
            # Extract markdown table segment
            m_table = part.replace("[STRUCTURED_START]", "").replace("[STRUCTURED_END]", "").strip()
            html_parts.append(markdown_table_to_html(m_table))
        else:
            # Escape HTML
            escaped = html.escape(part)
            # Convert escaped literal br strings back to actual <br /> tags
            escaped = escaped.replace("&lt;br&gt;", "<br />")
            escaped = escaped.replace("&lt;br /&gt;", "<br />")
            escaped = escaped.replace("&lt;br/&gt;", "<br />")
            
            # Format paragraphs
            html_parts.append(preserve_paragraphs(escaped))
            
    return "\n".join(html_parts)

def format_question_content(text: str, shared_context: Optional[str] = None) -> str:
    """
    Pure-renders question HTML content from text and optional shared context.
    """
    parts = []
    if shared_context and shared_context.strip():
        ctx_html = text_to_html(shared_context.strip())
        parts.append(f'<div class="shared-context">\n{ctx_html}\n</div>')
    
    if text and text.strip():
        parts.append(text_to_html(text.strip()))
        
    return "\n".join(parts)

def format_answer_content(text: str, working_notes: Optional[list] = None) -> str:
    """
    Pure-renders answer HTML content from main answer text and optional working notes.
    """
    parts = []
    if text and text.strip():
        parts.append(text_to_html(text.strip()))
        
    if working_notes:
        wn_parts = ['<div class="working-notes">', '<h4>Working Notes</h4>']
        for wn in working_notes:
            num = getattr(wn, 'number', '')
            title = getattr(wn, 'title', None)
            content = getattr(wn, 'content', str(wn))
            
            header_text = f"Working Note {num}" if num else "Working Note"
            if title:
                header_text += f": {title}"
            
            wn_parts.append('<div class="working-note-item">')
            wn_parts.append(f'<strong>{html.escape(header_text)}</strong>')
            wn_parts.append(text_to_html(content))
            wn_parts.append('</div>')
            
def _clean_cell_string(text: str) -> str:
    if not text:
        return ''
    text = text.replace('&lt;br&gt;', '<br />').replace('&lt;br/&gt;', '<br />').replace('&lt;br /&gt;', '<br />')
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

    # Replace backticks ` or ₹ with Rs. to prevent xhtml2pdf black square ■ rendering
    text = re.sub(r'[₹`]\s*(\d)', r'Rs. \1', text)
    text = re.sub(r'[₹`]', 'Rs. ', text)

    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    if re.match(r'^Col\d+$', text.strip(), re.IGNORECASE):
        return ''
    return text.strip()


def _deduplicate_cell_text(text: str) -> str:
    """
    Collapse repeated words and sub-phrases that PyMuPDF produces from merged cells.
    e.g. 'in in in' -> 'in', 'ParParticular' fragments, 'of of of' -> 'of', '1. 1. 1.' -> '1.'
    """
    if not text:
        return ''
    # 1. Collapse consecutively repeated tokens
    tokens = text.split()
    clean = []
    for tok in tokens:
        if not clean or tok.lower() != clean[-1].lower():
            clean.append(tok)
    return ' '.join(clean).strip()


def sanitize_stored_html_table(table_container_soup) -> str:
    from bs4 import BeautifulSoup
    from .table_processing import Cell, CellStyle, CellAlignment, Row, Table, TableProcessor

    table_tag = table_container_soup.find('table')
    if not table_tag:
        return str(table_container_soup)

    raw_grid = []
    tr_tags = table_tag.find_all('tr')
    if not tr_tags:
        return str(table_container_soup)

    for tr in tr_tags:
        row_cells = []
        cell_tags = tr.find_all(['th', 'td'])
        for cell in cell_tags:
            row_cells.append(_clean_cell_string(cell.get_text(separator=' ')))
        if any(c != '' for c in row_cells):
            raw_grid.append(row_cells)

    if not raw_grid:
        return str(table_container_soup)

    num_cols = max(len(r) for r in raw_grid)
    for r in raw_grid:
        while len(r) < num_cols:
            r.append('')

    # ── Step 1a: Left-anchor Column Deduplication ─────────────────────────────
    # PyMuPDF copies identical text into adjacent columns for merged cells.
    # For each column, find nearest non-empty column to the LEFT as reference.
    # Both cells must be non-empty; if ALL non-empty cells in this column match
    # the reference, this column is a duplicate → clear it.
    for c in range(1, num_cols):
        left_ref = None
        for prev in range(c - 1, -1, -1):
            if any(r[prev] != '' for r in raw_grid):
                left_ref = prev
                break
        if left_ref is None:
            continue
        filled_in_c = [(r_idx, r[c]) for r_idx, r in enumerate(raw_grid) if r[c] != '']
        if not filled_in_c:
            continue
        ref_vals = {r_idx: raw_grid[r_idx][left_ref] for r_idx, _ in filled_in_c}
        is_dup = all(
            ref_vals[r_idx] != ''
            and (val == ref_vals[r_idx]
                 or val in ref_vals[r_idx]
                 or ref_vals[r_idx] in val)
            for r_idx, val in filled_in_c
        )
        if is_dup:
            for r in raw_grid:
                r[c] = ''

    # ── Step 1b: Right-anchor Column Deduplication ────────────────────────────
    # Some PyMuPDF columns precede the "real" column with the same value.
    # e.g. col 1 = 81.00 and col 2 = 81.00 (same WDV value), but col 0 is text
    # so left-anchor pass didn't catch it.  Use right-anchor to catch these.
    for c in range(num_cols - 1):
        if not any(r[c] != '' for r in raw_grid):
            continue  # already empty
        right_ref = None
        for nxt in range(c + 1, num_cols):
            if any(r[nxt] != '' for r in raw_grid):
                right_ref = nxt
                break
        if right_ref is None:
            continue
        filled_in_c = [(r_idx, r[c]) for r_idx, r in enumerate(raw_grid) if r[c] != '']
        if not filled_in_c:
            continue
        ref_vals = {r_idx: raw_grid[r_idx][right_ref] for r_idx, _ in filled_in_c}
        is_dup = all(
            ref_vals[r_idx] != ''
            and (val == ref_vals[r_idx]
                 or val in ref_vals[r_idx]
                 or ref_vals[r_idx] in val)
            for r_idx, val in filled_in_c
        )
        if is_dup:
            for r in raw_grid:
                r[c] = ''

    # ── Step 1c: Row-level Same-Value Deduplication ───────────────────────────
    # PyMuPDF also duplicates text horizontally when one row cell overflows.
    # e.g. ['receivable', 'receivable', 'receivable', 'receivable'] → only col 0 kept.
    # Only applies to rows where ALL non-empty cells have the identical text value.
    for r in raw_grid:
        non_empty = [(c_idx, val) for c_idx, val in enumerate(r) if val != '']
        if len(non_empty) <= 1:
            continue
        # If every non-empty cell holds the same value, keep only the leftmost
        values = [val for _, val in non_empty]
        if len(set(v.lower() for v in values)) == 1:
            first_c = non_empty[0][0]
            for c_idx, _ in non_empty[1:]:
                r[c_idx] = ''

    data_row_indices = []
    for idx, r in enumerate(raw_grid):
        row_str = ' '.join(r)
        # Indian number format: 1,00,000 / 10,55,000  OR  decimal: 100.00
        if (re.search(r'\d{1,3}(?:,\d{2,3})+', row_str)
                or re.search(r'\(\d+\)', row_str)
                or re.search(r'\b\d+\.\d{2}\b', row_str)):
            data_row_indices.append(idx)

    if not data_row_indices:
        data_row_indices = list(range(1, len(raw_grid))) if len(raw_grid) > 1 else [0]

    data_rows = [raw_grid[i] for i in data_row_indices]

    # ── Step 3: Keep only columns used by data rows ──────────────────────────
    keep_cols = []
    for col_idx in range(num_cols):
        has_data = any(r[col_idx] != '' for r in data_rows)
        if has_data:
            keep_cols.append(col_idx)

    if not keep_cols:
        keep_cols = list(range(num_cols))

    pruned_grid = []
    for r in raw_grid:
        pruned_grid.append([r[i] for i in keep_cols])

    num_pruned_cols = len(keep_cols)

    # ── Step 4: Unified multi-row header ─────────────────────────────────────
    first_data_idx = data_row_indices[0] if data_row_indices else 1
    header_rows = pruned_grid[:first_data_idx]

    unified_headers = [''] * num_pruned_cols
    for c_idx in range(num_pruned_cols):
        parts = []
        for h_row in header_rows:
            txt = h_row[c_idx]
            if txt and txt != 'Rs.' and txt not in parts:
                parts.append(txt)
        unified_headers[c_idx] = _deduplicate_cell_text(' '.join(parts)).strip()

    # Default column-0 header when empty but rows have text content
    if not unified_headers[0] and any(raw_grid[i][keep_cols[0]] != '' for i in data_row_indices):
        unified_headers[0] = 'Particulars'

    # ── Step 5: Build Table model ────────────────────────────────────────────
    rows_model = []
    header_cells = [Cell(text=c, style=CellStyle.BOLD, alignment=CellAlignment.LEFT) for c in unified_headers]
    rows_model.append(Row(cells=header_cells, is_header=True))

    for idx in data_row_indices:
        r = pruned_grid[idx]
        if all(c == '' or c == 'Rs.' for c in r):
            continue

        # Apply per-cell deduplication on data rows too
        r = [_deduplicate_cell_text(c) for c in r]

        cells = []
        is_sec = r[0] != '' and not any(c != '' for c in r[1:])
        for c in r:
            style = CellStyle.BOLD if (is_sec or 'Total' in c) else CellStyle.NORMAL
            align = CellAlignment.RIGHT if re.match(r'^(?:Rs\.\s*[\d,]+|[\d,]+\.?\d*|\([\d,.]+\)|Nil)$', c) else CellAlignment.LEFT
            cells.append(Cell(text=c, style=style, alignment=align))

        rows_model.append(Row(cells=cells, is_header=False, is_section=is_sec))

    table_model = Table(rows=rows_model)
    return TableProcessor.render_to_html(table_model)


def clean_stored_html_tables(content: str) -> str:
    """
    Sanitizes pre-rendered <table> HTML stored in Question/Answer records.
    Removes dummy PyMuPDF headers (Col1, Col2), prunes empty layout columns,
    unifies multi-line headers, re-computes column widths, and uses Rs. for font safety.
    """
    if not content or '<table' not in content:
        return content

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, 'html.parser')
    table_containers = soup.find_all('div', class_='table-container')
    if not table_containers:
        table_containers = soup.find_all('table')

    for container in table_containers:
        new_table_html = sanitize_stored_html_table(container)
        new_soup = BeautifulSoup(new_table_html, 'html.parser')
        container.replace_with(new_soup)

    return str(soup)

