import re
from typing import List, Optional, Tuple
from .extraction_patterns import MARKS_PATTERNS, MARKS_EXCLUSION_PATTERNS

class MarksExtractor:
    """
    Tiered regex-based marks extraction with strict exclusions.
    """
    
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
                        
                    # 2. Positional Signal: Marks often appear at the end of a sub-question paragraph.
                    # We increase priority if followed by newline/end-of-block
                    is_at_end = False
                    after_text = text[end:end+10].strip()
                    if not after_text or after_text.startswith(("\n", "\r", "\f")):
                        is_at_end = True
                    
                    final_priority = priority + (10 if is_at_end else 0)
                    candidates.append((val, final_priority))
                    
                except (ValueError, IndexError):
                    continue
        
        if not candidates:
            return None
            
        # Priority first, then largest value (industrial standard for marking)
        candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
        return candidates[0][0]
