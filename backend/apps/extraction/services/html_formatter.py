import html
import re
from typing import Optional
from .table_processing import parse_markdown_to_table, TableProcessor

def escape_html(text: str) -> str:
    """
    Escape special characters to be HTML-safe.
    """
    return html.escape(text)

def clean_metadata_text(text: str, subject_name: Optional[str] = None, prepared_chapters: Optional[list] = None) -> str:
    """
    Strips metadata header lines (e.g. Part II-Questions and Answers, QUESTIONS,
    FINAL EXAMINATION, REVISION TEST PAPERS, MAY 2026 EXAMINATION, subject names, standalone chapter headers)
    from plain text while leaving question and answer content intact.
    """
    if not text:
        return ""
    from .extraction_patterns import DOCUMENT_METADATA_PATTERNS
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_meta = False
        for pat in DOCUMENT_METADATA_PATTERNS:
            if re.match(pat, stripped):
                is_meta = True
                break
        if not is_meta and subject_name and re.match(r"(?i)^[ \t]*" + re.escape(subject_name) + r"\s*$", stripped):
            is_meta = True

        if not is_meta and prepared_chapters:
            # MCQ options (Option (c)...) or answer choices are NEVER chapter headers
            if not re.match(r"(?i)^\s*(?:Option\b|Ans\.?|Choice|Key|\([a-eA-E]\))", stripped):
                from .chapter_mapper import map_question_to_chapter
                ch = map_question_to_chapter(stripped, prepared_chapters)
                if ch:
                    if re.match(r"(?i)^[ \t]*(?:Ind\s*AS|AS|SA|CARO|Chapter|Section)\s*\d+[\s\-–—:]", stripped) or (ch.chapter_name and stripped.strip().lower() == ch.chapter_name.lower()):
                        is_meta = True

        if not is_meta:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def preserve_paragraphs(text: str) -> str:
    """
    Convert double newlines into simple HTML paragraphs and replace single newlines with br tags,
    skipping metadata noise header paragraphs.
    """
    if not text.strip():
        return ""
    
    from .extraction_patterns import DOCUMENT_METADATA_PATTERNS
    # Split by double or more newlines to identify paragraphs, handling spaces
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    
    # Wrap each paragraph in <p> tags and convert internal newlines to <br />
    html_paragraphs = []
    for p in paragraphs:
        plain_p = re.sub(r"<[^>]+>", "", p).strip()
        is_meta = False
        for pat in DOCUMENT_METADATA_PATTERNS:
            if re.match(pat, plain_p):
                is_meta = True
                break
        if is_meta:
            continue

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
            # Extract table segment (could be HTML or Markdown)
            m_table = part.replace("[STRUCTURED_START]", "").replace("[STRUCTURED_END]", "").strip()
            if m_table.startswith("<div") or "<table" in m_table:
                html_parts.append(m_table)
            else:
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
        wn_parts.append('</div>')
        parts.append("\n".join(wn_parts))
        
    return "\n".join(parts)

            
def _clean_cell_string(text: str) -> str:
    if not text:
        return ''
    text = text.replace('&lt;br&gt;', ' ').replace('&lt;br/&gt;', ' ').replace('&lt;br /&gt;', ' ')
    text = text.replace('<br>', ' ').replace('<br/>', ' ').replace('<br />', ' ').replace('\n', ' ')
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

    # Replace backticks ` or ₹ with Rs. to prevent xhtml2pdf black square ■ rendering
    text = re.sub(r'[₹`]\s*(\d)', r'Rs. \1', text)
    text = re.sub(r'[₹`]', 'Rs. ', text)

    # Clean up duplicate currency patterns like Rs. (Rs.) -> (Rs.)
    text = re.sub(r'Rs\.\s*\(Rs\.\)', '(Rs.)', text, flags=re.IGNORECASE)
    text = re.sub(r'\bRs\.\s+Rs\.\b', 'Rs.', text, flags=re.IGNORECASE)

    # Clean up formula suffixes in header titles e.g. "Rs. b=1,00,000 x 6%" or "Rs. c=a x 5.7317%"
    text = re.sub(r'\s*(?:Rs\.|₹)?\s*[a-e]\s*=\s*.*$', '', text, flags=re.IGNORECASE)

    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    if re.match(r'^Col\d+$', text.strip(), re.IGNORECASE):
        return ''
    return re.sub(r'\s+', ' ', text).strip()


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

    if table_container_soup.find('img') or table_container_soup.get('data-is-complex') == 'true' or table_container_soup.get('data-crop-path') or table_container_soup.get('data-table-provenance'):
        return str(table_container_soup)

    table_tag = table_container_soup if getattr(table_container_soup, 'name', None) == 'table' else table_container_soup.find('table')
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

    # ── Step 1a: Split concatenated Header 0 (e.g. 'Particulars Opening Carrying amount a' or 'Particulars Closing balance') ─
    h0 = raw_grid[0][0].strip()
    m_h = re.match(r'^(Particulars?|Date|Item)\s+(Opening\s+Carrying\s+amount.*|Opening\s+Balance.*|Closing\s+balance.*|Carrying\s+amount.*)$', h0, re.IGNORECASE)
    if m_h:
        raw_grid[0][0] = m_h.group(1)
        raw_grid[0].insert(1, m_h.group(2))
        num_cols = max(len(r) for r in raw_grid)
        for r in raw_grid:
            while len(r) < num_cols:
                r.append('')

    # ── Step 1a-2: Fold 'Shares' from Row 1 into Header 1 ('Number of' + 'Shares' -> 'Number of Shares') ──
    if len(raw_grid) > 1 and any(cell.strip().lower() == 'shares' for cell in raw_grid[1]):
        for c in range(num_cols):
            if raw_grid[1][c].strip().lower() == 'shares':
                raw_grid[0][c] = (raw_grid[0][c].strip() + ' Shares').strip()
                raw_grid[1][c] = ''
        if all(cell == '' for cell in raw_grid[1]):
            raw_grid.pop(1)

    # ── Step 1a-3: Balance Sheet 4-column shift repair where Item Particulars is in Col 2 instead of Col 1 ──
    header_str = ' '.join(raw_grid[0])
    if any(k in header_str for k in ['ASSETS', 'Non-Current Assets', 'Current Assets', 'EQUITY AND LIABILITIES']):
        raw_grid[0] = ['Particulars', 'Note No.', 'Amount (Rs.)', 'Amount (Rs.)']
        for r in raw_grid[1:]:
            if len(r) >= 4 and re.search(r'[A-Za-z]{3,}', r[2]) and not r[1]:
                r[1] = r[2]
                r[2] = ''
            if len(r) >= 4 and r[2] and not r[3] and re.match(r'^[\d,]+$', r[2]):
                r[3] = r[2]
                r[2] = ''

    # ── Step 1b: Split PyMuPDF concatenated body cell values ─────────────────────
    for r in raw_grid[1:]:
        # 1. Split Company Name + Investment Amount in cell 0
        m_co = re.match(r'^([A-Z]\s+Ltd\.|[A-Za-z0-9\s]+Co\.|[A-Za-z0-9\s]+Ltd\.)\s+([\d,]+)$', r[0].strip())
        if m_co:
            r[0] = m_co.group(1).strip()
            r.insert(1, m_co.group(2).strip())
            num_cols = max(len(r_sub) for r_sub in raw_grid)
            for r_sub in raw_grid:
                while len(r_sub) < num_cols:
                    r_sub.append('')

        # 2. Split Date + Number in cell 0 (e.g. '31 Mar 2XX1 1,02,000' -> '31 Mar 2XX1', '1,02,000')
        date_m = re.match(r'^(\d{1,2}\s+[A-Za-z]+\s+(?:2X{1,2}\d|2X\d{2}|2\d{3}|\d{4}))\s+([\d,]+)$', r[0].strip(), re.IGNORECASE)
        if date_m:
            r[0] = date_m.group(1)
            r.insert(1, date_m.group(2))
            num_cols = max(len(r_sub) for r_sub in raw_grid)
            for r_sub in raw_grid:
                while len(r_sub) < num_cols:
                    r_sub.append('')

        # 3. Split trailing amount from text in cell 0 when cell 1 is empty
        if len(r) >= 3 and r[1] == '' and r[2] != '':
            m = re.match(r'^(.*?)\s+(\(?[0-9,]{3,}\)?)$', r[0].strip())
            if m:
                r[0] = m.group(1).strip()
                r[1] = m.group(2).strip()

        # 4. Split two concatenated amounts in cell 1 when cell 2 is empty
        for c in range(len(r) - 1):
            if r[c] != '' and r[c+1] == '':
                amounts = re.findall(r'\(?[0-9,]{3,}(?:\.\d+)?\)?', r[c])
                if len(amounts) == 2:
                    idx1 = r[c].find(amounts[0])
                    idx2 = r[c].find(amounts[1])
                    if idx2 > idx1:
                        prefix_text = r[c][:idx2].strip()
                        first_amt = amounts[0]
                        second_amt = amounts[1]
                        if prefix_text == first_amt or not re.search(r'[A-Za-z]', prefix_text):
                            r[c] = first_amt
                        else:
                            r[c] = prefix_text
                        r[c+1] = second_amt

    # ── Step 1c: Fold multi-row header titles (e.g. 'Profit (loss)' + 'FY 20X1-' + '20X2') ──
    header_rows_count = 1
    for idx in range(1, min(4, len(raw_grid))):
        r = raw_grid[idx]
        if any(tok in ' '.join(r) for tok in ['for the', 'FY 20X', '20X1', '20X2', '20X3', '20X4', 'Standalone', 'annual payment']):
            header_rows_count = idx + 1
        else:
            break

    if header_rows_count > 1:
        folded_header = []
        for c in range(num_cols):
            tokens = [raw_grid[r_idx][c].strip() for r_idx in range(header_rows_count) if raw_grid[r_idx][c].strip()]
            folded_header.append(' '.join(tokens).strip())
        raw_grid = [folded_header] + raw_grid[header_rows_count:]

    # ── Step 1c: Merge columns with EMPTY headers into primary Amount column ─
    header_row = raw_grid[0]
    while len(header_row) < num_cols:
        header_row.append('')
    for c in range(1, num_cols):
        if header_row[c].strip() == '':
            target_col = None
            for c2 in range(c + 1, num_cols):
                if c2 < len(header_row) and header_row[c2].strip() != '':
                    target_col = c2
                    break
            if target_col is not None:
                for r in raw_grid:
                    if c < len(r) and target_col < len(r) and r[c] != '':
                        if r[target_col] == '' or r[target_col] == r[c]:
                            r[target_col] = r[c]
                            r[c] = ''

    # ── Step 1d: Horizontal Row-level Duplicate Cell Clearing ─────────────────
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

    # ── Step 5: HEADER ROW IDENTIFICATION ────────────────────────────────────
    # Search first 3 rows for the row containing column header labels (e.g. 'Dr.', 'Cr.', 'Pre- acquisition')
    header_row_idx = 0
    for idx, r in enumerate(pruned_grid):
        if idx < 3:
            non_num_header_cols = sum(
                1 for c in range(1, num_pruned_cols)
                if r[c] != '' and not re.search(r'^\(?[0-9,\.]+\)?$', r[c].strip())
            )
            if non_num_header_cols > 0:
                header_row_idx = idx
                break

    header_row = pruned_grid[header_row_idx]
    data_rows = pruned_grid[header_row_idx + 1:]

    # Clean header row titles
    unified_headers = []
    for c_idx in range(num_pruned_cols):
        txt = header_row[c_idx].strip()
        if not txt:
            txt = 'Particulars' if c_idx == 0 else 'Amount (Rs.)'
        unified_headers.append(txt)

    # ── Step 6: Build Table model ────────────────────────────────────────────
    rows_model = []
    header_cells = [Cell(text=c, style=CellStyle.BOLD, alignment=CellAlignment.LEFT) for c in unified_headers]
    rows_model.append(Row(cells=header_cells, is_header=True))

    for r in data_rows:
        if all(c == '' or c == 'Rs.' for c in r):
            continue

        r = [_deduplicate_cell_text(c) for c in r]

        cells = []
        is_sec = r[0] != '' and not any(c != '' for c in r[1:])
        for c in r:
            style = CellStyle.BOLD if (is_sec or 'Total' in c or 'Total' in r[0]) else CellStyle.NORMAL
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

    # Strip any hardcoded <colgroup>...</colgroup> overrides that force narrow 1cm columns in xhtml2pdf
    content = re.sub(r'<colgroup>.*?</colgroup>', '', content, flags=re.DOTALL | re.IGNORECASE)

    # Unwrap invalid <p><div class="table-container">...</div></p> and <p><table...</p>
    content = re.sub(r'<p[^>]*>\s*(<div[^>]*class=["\']table-container["\'].*?</div>)\s*</p>', r'\1', content, flags=re.DOTALL)
    content = re.sub(r'<p[^>]*>\s*(<table.*?</table>)\s*</p>', r'\1', content, flags=re.DOTALL)

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

