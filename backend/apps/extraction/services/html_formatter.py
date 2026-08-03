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
            
        wn_parts.append('</div>')
        parts.append("\n".join(wn_parts))
        
    return "\n".join(parts)

