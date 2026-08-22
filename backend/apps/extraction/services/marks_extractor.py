import re
import logging
from typing import List, Optional, Tuple
from .types import ParserConfig

logger = logging.getLogger(__name__)


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
            
        candidates: List[Tuple[int, int, int]] = [] # (value, priority, start_offset)
        
        # Priority mapping based on pattern order (1 to 7)
        for i, regex in enumerate(self.config.marks_patterns):
            priority = 100 - i
            matches = list(regex.finditer(text))
            
            for m in matches:
                try:
                    val = int(m.group(1))
                    start, end = m.span()
                    
                    # 1. Exclusion Check: Verify if candidate digits overlap with an excluded construct
                    is_excluded = False
                    for excl in self.config.marks_exclusion_patterns:
                        for excl_match in excl.finditer(text):
                            excl_start, excl_end = excl_match.span()
                            if excl_start < end and start < excl_end:
                                is_excluded = True
                                break
                        if is_excluded:
                            break
                    if is_excluded:
                        logger.debug("Rejected marks candidate | candidate=%s | reason=exclusion_pattern | start_offset=%d", m.group(0), start)
                        continue
                        
                    # 2. Positional Validation for Weaker Patterns (e.g. (5), [5], 5M) to filter list items/measurements
                    is_weak = "marks" not in m.group(0).lower()
                    if is_weak:
                        # CR line ending support
                        line_start_idx_n = text.rfind('\n', 0, start)
                        line_start_idx_r = text.rfind('\r', 0, start)
                        line_start_idx = max(line_start_idx_n, line_start_idx_r)
                        
                        if line_start_idx == -1:
                            line_start_idx = 0
                        else:
                            line_start_idx += 1
                        
                        # Find the rest of the text on the same line
                        line_end_idx_n = text.find('\n', end)
                        line_end_idx_r = text.find('\r', end)
                        line_end_idx = len(text)
                        indices = [idx for idx in (line_end_idx_n, line_end_idx_r) if idx != -1]
                        if indices:
                            line_end_idx = min(indices)
                            
                        before_on_same_line = text[line_start_idx:start].strip()
                        after_on_same_line = text[end:line_end_idx].strip()
                        
                        # If alone on line at start of a paragraph and not at the end of the question, it's a list bullet
                        if not before_on_same_line and end < len(text) - 20:
                            logger.debug(
                                "Rejected marks candidate | candidate=%s | reason=list_bullet_at_start_of_line | start_offset=%d",
                                m.group(0), start
                            )
                            continue

                        # If there are word characters after the match on the same line,
                        # only allow them if they consist entirely of transition words (OR, Compulsory, etc.)
                        if re.search(r'\w', after_on_same_line):
                            words = re.findall(r'\b\w+\b', after_on_same_line.upper())
                            allowed = {"OR", "COMPULSORY", "ATTEMPT", "ANY", "ONE", "MARKS", "MARK"}
                            if not all(w in allowed for w in words):
                                logger.debug(
                                    "Rejected marks candidate | candidate=%s | reason=invalid_trailing_words | trailing_text=%s | start_offset=%d",
                                    m.group(0), after_on_same_line[:30], start
                                )
                                continue

                    candidates.append((val, priority, start))
                    
                except (ValueError, IndexError):
                    continue
        
        if not candidates:
            return None
            
        # Priority first, then later occurrence (larger start offset) when priorities are equal
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return candidates[0][0]
