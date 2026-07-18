import html
import re

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
    Parses a simple markdown table into a semantic HTML table.
    """
    lines = [line.strip() for line in markdown_table.strip().split('\n') if line.strip()]
    if not lines:
        return ""
    
    html_rows = []
    has_header = False
    
    for line in lines:
        if line.startswith('|') and line.endswith('|'):
            # Split cells and omit empty edge cells
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            
            # Skip separator line like |---|---| or |:---|:---|
            if all(re.match(r'^[-:]+$', cell) for cell in cells):
                continue
            
            if not has_header:
                header_cells = "".join([f"<th>{cell}</th>" for cell in cells])
                html_rows.append(f"<tr>{header_cells}</tr>")
                has_header = True
            else:
                body_cells = "".join([f"<td>{cell}</td>" for cell in cells])
                html_rows.append(f"<tr>{body_cells}</tr>")
                
    if not html_rows:
        return ""
        
    return f'<div class="table-container"><table class="structured-table">{"".join(html_rows)}</table></div>'

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
