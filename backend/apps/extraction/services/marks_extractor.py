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
        
        # Priority mapping based on pattern order (1 to 5 as requested)
        for i, regex in enumerate(self.config.marks_patterns):
            priority = 100 - i
            matches = list(regex.finditer(text))
            
            for m in matches:
                try:
                    # In our custom regex patterns, the value is in group 1
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
                        
                    # 2. Positional Validation for Weaker Patterns (e.g. (5), [5], 5M)
                    is_weak = "marks" not in m.group(0).lower()
                    if is_weak:
                        # Check if the match is preceded by any non-whitespace character on the same line.
                        # If preceded only by whitespace, it is at the start of a line (like a list item)
                        # and is rejected.
                        line_start_idx = text.rfind('\n', 0, start)
                        if line_start_idx == -1:
                            line_start_idx = 0
                        else:
                            line_start_idx += 1
                        before_on_same_line = text[line_start_idx:start]
                        
                        if not re.search(r'\S', before_on_same_line):
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
