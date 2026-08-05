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
    # ── Step 1: Horizontal Row-level Duplicate Cell Clearing ─────────────────
    for r in raw_grid:
        left_val = None
        for c in range(len(r)):
            cell = r[c]
            if cell:
                if left_val and cell.strip().lower() == left_val.strip().lower():
                    r[c] = ''
                else:
                    left_val = cell

    # Find main text column (first column containing text strings > 15 chars)
    main_text_col = 0
    for c in range(num_cols):
        if any(len(raw_grid[r_idx][c]) > 15 for r_idx in range(len(raw_grid))):
            main_text_col = c
            break

    # ── Step 2: Merge Prefix/Index Columns into main_text_col ─────────────────
    # Columns to the left of main_text_col that contain item numbers ('1.', 'a.'), Roman numerals, or section labels ('Total')
    for r in raw_grid:
        prefix_parts = []
        for c in range(main_text_col):
            val = r[c]
            if val:
                prefix_parts.append(val)
                r[c] = ''
        if prefix_parts:
            existing_text = r[main_text_col]
            r[main_text_col] = (' '.join(prefix_parts) + ' ' + existing_text).strip()

    # ── Step 3: Merge non-overlapping amount columns to the right of main_text_col ─
    amount_cols = [c for c in range(main_text_col + 1, num_cols)]
    if len(amount_cols) > 1:
        for i in range(len(amount_cols) - 1):
            c1 = amount_cols[i]
            c2 = amount_cols[i + 1]
            overlap = any(r[c1] != '' and r[c2] != '' for r in raw_grid)
            if not overlap:
                for r in raw_grid:
                    if r[c1] != '':
                        r[c2] = r[c1]
                        r[c1] = ''

    # ── Step 4: Data-density column pruning ──────────────────────────────────
    # Keep columns that have content in at least 1 row (or non-empty cell)
    keep_cols = []
    for c in range(num_cols):
        has_content = any(r[c] != '' for r in raw_grid)
        if has_content:
            keep_cols.append(c)

    if not keep_cols:
        keep_cols = list(range(num_cols))

    pruned_grid = []
    for r in raw_grid:
        pruned_grid.append([r[i] for i in keep_cols])

    num_pruned_cols = len(keep_cols)

    # ── Step 5: Separate header vs data rows ─────────────────────────────────
    data_row_indices = []
    for idx, r in enumerate(pruned_grid):
        row_str = ' '.join(r)
        if (re.search(r'\d', row_str) or any(r[c] != '' for c in range(1, num_pruned_cols))):
            data_row_indices.append(idx)

    if not data_row_indices:
        data_row_indices = list(range(1, len(pruned_grid))) if len(pruned_grid) > 1 else [0]

    # ── Step 6: Unified multi-row header ─────────────────────────────────────
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

    # Default headers for column 0 and column 1 if empty
    if not unified_headers[0] and any(pruned_grid[i][0] != '' for i in data_row_indices):
        unified_headers[0] = 'Particulars'

    # ── Step 7: Build Table model ────────────────────────────────────────────
    rows_model = []
    header_cells = [Cell(text=c, style=CellStyle.BOLD, alignment=CellAlignment.LEFT) for c in unified_headers]
    rows_model.append(Row(cells=header_cells, is_header=True))

    for idx in data_row_indices:
        r = pruned_grid[idx]
        if all(c == '' or c == 'Rs.' for c in r):
            continue

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

