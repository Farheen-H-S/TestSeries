import re
from typing import List, Optional

class HeaderValidator:
    """
    Handles structural validation, hierarchy enforcement, and false-positive rejection
    for potential question and answer headers.
    """
    
    ROMAN_REGEX = re.compile(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv)$', re.IGNORECASE)

    def is_valid(self, match: re.Match, path: List[str], current_stack: List[str], full_text: str) -> bool:
        """
        Validates if a potential header is structurally sound and logically follows the current hierarchy.
        """
        if not path:
            return False
            
        raw_header = match.group(0)
        start_idx = match.start()
        
        # 1. Structural Validation (Start of Line)
        if not self._is_start_of_line(start_idx, full_text):
            # Only allow if it's a "strong" header (e.g. "Question 1")
            if not self._is_strong_header(raw_header):
                return False

        # 2. Hierarchy Validation
        if not self._is_logical_transition(path, current_stack):
            return False

        return True

    def _is_start_of_line(self, idx: int, text: str) -> bool:
        if idx == 0:
            return True
        # Check backward for newline, allowing leading whitespace/tabs
        check_idx = idx - 1
        while check_idx >= 0:
            char = text[check_idx]
            if char == '\n':
                return True
            if char not in (' ', '\t', '\r', '\f'):
                return False
            check_idx -= 1
        return True

    def _is_strong_header(self, raw_header: str) -> bool:
        upper = raw_header.upper()
        return "QUESTION" in upper or "ANS" in upper or "SOL" in upper or "Q." in upper

    def _is_logical_transition(self, new_path: List[str], current_stack: List[str]) -> bool:
        """
        Enforces legal hierarchy transitions.
        Allowed:
        1 -> 2
        1 -> 1(a)
        1(a) -> 1(b)
        1(a) -> 1(a)(i)
        Reject:
        1 -> (i)
        (c) -> (a)
        """
        if not current_stack:
            # We assume the first thing MUST be a main question number (digit)
            # OR a sub-question if it's (a) - some documents start with (a)
            return new_path[0].isdigit() or new_path[0] == 'a'

        # Decompose the new path
        main, alpha, roman = self._decompose_path(new_path)
        c_main, c_alpha, c_roman = self._decompose_path(current_stack)

        if main:
            # Transitioning to a new MAIN question (e.g. 1 -> 2)
            # We allow non-sequential digits because OCR might miss one or paper might skip
            return True 
        
        if alpha and not roman:
            # Transitioning to a SUB question (e.g. (a) -> (b) or 1 -> (a))
            if not c_main: return False # Impossible
            # If we already have a sub, check if it's sequential or nested?
            # Actually, alpha follows main. 
            return True # Lenient for now, but avoids (i) -> (a)
            
        if roman:
            # Transitioning to SUB_SUB (e.g. (i) -> (ii) or (a) -> (i))
            if not c_alpha: 
                # (i) cannot follow 1 without (a) or similar intermediate level in most ICAI papers
                # However, some papers do 1 -> (i). We'll allow it if main exists.
                return c_main is not None
            return True

        return False

    def _decompose_path(self, path: List[str]):
        main = path[0] if path[0].isdigit() else None
        alpha = None
        roman = None
        
        for p in path:
            if p.isdigit(): main = p
            elif self.ROMAN_REGEX.match(p): roman = p
            elif len(p) == 1 and p.isalpha(): alpha = p
            
        return main, alpha, roman
