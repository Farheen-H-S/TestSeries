import re


def sanitize_filename(title: str, suffix: str = "") -> str:
    """
    Convert a paper title into a safe, readable filename.

    Rules:
    - strip() the input first
    - Preserve hyphens (-) and underscores (_)
    - Replace spaces with underscores
    - Remove illegal filename characters: \\ / : * ? " < > |
    - Collapse consecutive underscores into one
    - Trim leading/trailing underscores and hyphens
    - Limit to 100 characters (before suffix)
    - Append suffix (e.g. '_Answer_Sheet') + '.pdf'

    The result is guaranteed to be non-empty because GenerationFilterSerializer
    enforces that paper_title contains at least one alphanumeric character.
    """
    # Strip leading/trailing whitespace
    name = title.strip()

    # Replace spaces with underscores
    name = name.replace(' ', '_')

    # Remove illegal filename characters (keep hyphens and underscores)
    name = re.sub(r'[\\/:*?"<>|,#@!$%^&+=\[\]{}\'`~]', '', name)

    # Collapse consecutive underscores
    name = re.sub(r'_+', '_', name)

    # Trim leading/trailing underscores and hyphens
    name = name.strip('_-')

    # Limit to 100 chars
    name = name[:100]

    # Strip again in case truncation left trailing _ or -
    name = name.strip('_-')

    return f"{name}{suffix}.pdf"
