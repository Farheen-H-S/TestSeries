import re
from typing import List, Optional, Tuple
from .extraction_patterns import MARKS_PATTERNS, MARKS_EXCLUSION_PATTERNS

class MarksExtractor:
    """
    Tiered regex-based marks extraction with strict exclusions.
    """
    
    def __init__(self, patterns=None, exclusions=None):
        self.patterns = [(re.compile(p, re.IGNORECASE), 100 - i) 
                         for i, p in enumerate(patterns or MARKS_PATTERNS)]
        self.exclusions = [re.compile(p, re.IGNORECASE) 
                           for p in (exclusions or MARKS_EXCLUSION_PATTERNS)]

    def extract(self, text: str) -> Optional[int]:
        """
        Collects all candidates, validates them against exclusions, and picks the highest priority match.
        """
        candidates: List[Tuple[int, int]] = [] # (value, priority)
        
        for regex, priority in self.patterns:
            matches = list(regex.finditer(text))
            for m in matches:
                val_str = m.group(1)
                try:
                    val = int(val_str)
                    
                    # Validate against exclusions
                    is_excluded = False
                    # We check if the match region or its immediate context matches an exclusion
                    # Actually, simple exclusion search in the whole text is too broad, 
                    # but check if the specific number is part of an excluded pattern.
                    start, end = m.span()
                    # Check a small window around the match
                    window_start = max(0, start - 10)
                    window_end = min(len(text), end + 10)
                    context = text[window_start:window_end]
                    
                    for excl in self.exclusions:
                        if excl.search(context):
                            is_excluded = True
                            break
                            
                    if not is_excluded:
                        candidates.append((val, priority))
                except ValueError:
                    continue
        
        if not candidates:
            return None
            
        # Pick the one with highest priority. If tie, pick largest value.
        candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
        return candidates[0][0]
