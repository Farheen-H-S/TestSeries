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
    Convert plain text to HTML. Converts structured markdown tables and escapes normal text safely.
    """
    if not text:
        return ""
        
    # 1. Extract structured table blocks and replace with placeholders
    placeholders = []
    
    def table_replacer(match):
        markdown_table = match.group(1)
        html_table = markdown_table_to_html(markdown_table)
        placeholder = f"__TABLE_PLACEHOLDER_{len(placeholders)}__"
        placeholders.append(html_table)
        return placeholder

    # Find [STRUCTURED_START]...[STRUCTURED_END] using DOTALL so it matches multiline
    pattern = re.compile(r"\[STRUCTURED_START\](.*?)\[STRUCTURED_END\]", re.DOTALL)
    processed_text = pattern.sub(table_replacer, text)
    
    # 2. Escape HTML for safety
    escaped_text = html.escape(processed_text)
    
    # 3. Format as paragraphs
    html_content = preserve_paragraphs(escaped_text)
    
    # 4. Convert escaped literal br strings back to actual <br /> tags
    html_content = html_content.replace("&lt;br&gt;", "<br />")
    html_content = html_content.replace("&lt;br /&gt;", "<br />")
    html_content = html_content.replace("&lt;br/&gt;", "<br />")
    
    # 5. Restore the HTML table placeholders
    for idx, html_table in enumerate(placeholders):
        # We need to replace the escaped version of the placeholder
        escaped_placeholder = html.escape(f"__TABLE_PLACEHOLDER_{idx}__")
        html_content = html_content.replace(escaped_placeholder, html_table)
        # Also handle unescaped just in case
        html_content = html_content.replace(f"__TABLE_PLACEHOLDER_{idx}__", html_table)
        
    return html_content
