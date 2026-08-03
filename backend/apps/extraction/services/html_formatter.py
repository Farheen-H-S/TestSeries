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
    text = re.sub(r'`\s*(\d)', r'₹ \1', text)
    text = re.sub(r'`', '₹', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    if re.match(r'^Col\d+$', text.strip(), re.IGNORECASE):
        return ''
    return text.strip()


def sanitize_stored_html_table(table_container_soup) -> str:
    from bs4 import BeautifulSoup
    from .table_processing import Cell, CellStyle, CellAlignment, Row, Table

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

    # Identify real data rows (rows containing numbers/amounts or clear data values)
    data_rows = []
    for r in raw_grid:
        row_str = ' '.join(r)
        if re.search(r'\d{1,3}(?:,\d{2,3})+', row_str) or re.search(r'\(\d+\)', row_str):
            data_rows.append(r)

    if not data_rows:
        data_rows = raw_grid[1:] if len(raw_grid) > 1 else raw_grid

    # Keep columns that have content in AT LEAST ONE real data row
    keep_cols = []
    for col_idx in range(num_cols):
        has_data = any(r[col_idx] != '' for r in data_rows) if data_rows else any(r[col_idx] != '' for r in raw_grid)
        if has_data:
            keep_cols.append(col_idx)

    if not keep_cols:
        keep_cols = list(range(num_cols))

    pruned_grid = []
    for r in raw_grid:
        pruned_grid.append([r[i] for i in keep_cols])

    rows_model = []
    header_cells = [Cell(text=c, style=CellStyle.BOLD, alignment=CellAlignment.LEFT) for c in pruned_grid[0]]
    rows_model.append(Row(cells=header_cells, is_header=True))

    for r in pruned_grid[1:]:
        is_dup_header = all(c == '' or c in pruned_grid[0] or 'Company' in c or 'Invested' in c or 'for the' in c for c in r)
        if is_dup_header and not any(re.search(r'\d', c) for c in r):
            continue

        cells = []
        is_sec = r[0] != '' and not any(c != '' for c in r[1:])
        for c in r:
            style = CellStyle.BOLD if (is_sec or 'Total' in c) else CellStyle.NORMAL
            align = CellAlignment.RIGHT if re.match(r'^(?:[₹\-\u2013\d,\s\(\)]+|Nil)$', c) else CellAlignment.LEFT
            cells.append(Cell(text=c, style=style, alignment=align))

        rows_model.append(Row(cells=cells, is_header=False, is_section=is_sec))

    table_model = Table(rows=rows_model)
    return TableProcessor.render_to_html(table_model)


def clean_stored_html_tables(content: str) -> str:
    """
    Sanitizes pre-rendered <table> HTML stored in Question/Answer records.
    Removes dummy PyMuPDF headers (Col1, Col2), prunes empty layout columns,
    re-computes column widths, and replaces backtick ` with ₹.
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

