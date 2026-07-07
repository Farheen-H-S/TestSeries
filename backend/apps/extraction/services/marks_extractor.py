import re
from typing import List, Optional, Tuple
from .types import ParserConfig

class MarksExtractor:
    """
    Tiered regex-based marks extraction with strict exclusions and structural validation.
    """
    
    def __init__(self, config: ParserConfig):
        # Already compiled in config
        self.config = config

    def extract(self, text: str) -> Optional[int]:
        """
        Collects all candidates from the text, validates them with large context, and picks the best match.
        """
        if not text:
            return None
            
        candidates: List[Tuple[int, int]] = [] # (value, priority)
        
        # Priority mapping based on pattern order (1 to 7)
        for i, regex in enumerate(self.config.marks_patterns):
            priority = 100 - i
            matches = list(regex.finditer(text))
            
            for m in matches:
                try:
                    val = int(m.group(1))
                    
                    # Structural Validation
                    # Check a large window around the match (50 chars)
                    start, end = m.span()
                    window_start = max(0, start - 50)
                    window_end = min(len(text), end + 50)
                    context = text[window_start:window_end]
                    
                    # 1. Exclusion Check
                    is_excluded = False
                    for excl in self.config.marks_exclusion_patterns:
                        if excl.search(context):
                            is_excluded = True
                            break
                    if is_excluded:
                        continue
                        
                    # 2. Positional Validation for Weaker Patterns (e.g. (5), [5], 5M) to filter list items
                    is_weak = "marks" not in m.group(0).lower()
                    if is_weak:
                        line_start_idx = text.rfind('\n', 0, start)
                        line_start_idx = max(0, line_start_idx)
                        before_on_same_line = text[line_start_idx:start]
                        
                        is_preceded = bool(re.search(r'\S', before_on_same_line))
                        if not is_preceded:
                            # It starts the line.
                            # Reject if followed by word characters on the same line (which would be a list item like "(1) Point")
                            line_end_idx = text.find('\n', end)
                            if line_end_idx == -1:
                                line_end_idx = len(text)
                            after_on_same_line = text[end:line_end_idx]
                            if re.search(r'\w', after_on_same_line):
                                continue

                    # Calculate if it's near the end of a line or paragraph
                    after_text = text[end:end+40]
                    is_at_end = (not re.search(r'\w', after_text)) or ("\n" in after_text[:15])
                    
                    final_priority = priority + (15 if is_at_end else 0)
                    candidates.append((val, final_priority))
                    
                except (ValueError, IndexError):
                    continue
        
        if not candidates:
            return None
            
        # Priority first, then largest value (industrial standard for marking)
        candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
        return candidates[0][0]
