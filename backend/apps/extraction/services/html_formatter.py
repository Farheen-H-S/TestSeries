import html
import re

def escape_html(text: str) -> str:
    """
    Escape special characters to be HTML-safe.
    """
    return html.escape(text)

def preserve_paragraphs(text: str) -> str:
    """
    Convert double newlines into simple HTML paragraphs.
    """
    if not text.strip():
        return ""
    
    # Split by double or more newlines to identify paragraphs, handling spaces
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    
    # Wrap each paragraph in <p> tags
    formatted_html = "\n".join([f"<p>{p}</p>" for p in paragraphs])
    
    return formatted_html

def text_to_html(text: str) -> str:
    """
    Convert plain text to simple HTML with paragraph preservation.
    """
    # First escape the text for safety
    escaped_text = escape_html(text)
    
    # Then format as paragraphs
    return preserve_paragraphs(escaped_text)
