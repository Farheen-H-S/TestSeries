import re
from typing import List, Optional, NamedTuple
from .hierarchy_utils import HierarchyUtils

class ValidationResult(NamedTuple):
    is_valid: bool
    reason: Optional[str] = None

class HeaderValidator:
    """
    Handles structural validation, hierarchy enforcement, and false-positive rejection
    for potential question and answer headers.
    """
    
    def is_valid(self, match: re.Match, path: List[str], current_stack: List[str], full_text: str) -> ValidationResult:
        """
        Validates if a potential header is structurally sound and logically follows the current hierarchy.
        Returns ValidationResult with a detailed reason for rejection.
        """
        if not path:
            return ValidationResult(False, "failed OCR normalization / no identifier found")
            
        raw_header = match.group(0)
        start_idx = match.start()
        
        # 1. Structural Validation (Start of Line)
        if not self._is_start_of_line(start_idx, full_text):
            # Only allow if it's a "strong" header (e.g. "Question 1")
            if not self._is_strong_header(raw_header):
                return ValidationResult(False, "not start of line")

        # 2. Hierarchy Validation
        return self._check_logical_transition(path, current_stack)

    def _is_start_of_line(self, idx: int, text: str) -> bool:
        if idx == 0:
            return True
        # Check backward for newline, allowing leading horizontal whitespace
        check_idx = idx - 1
        while check_idx >= 0:
            char = text[check_idx]
            if char == '\n':
                return True
            if char not in (' ', '\t'):
                return False
            check_idx -= 1
        return True

    def _is_strong_header(self, raw_header: str) -> bool:
        upper = raw_header.upper()
        # Strong markers that can appear without being at start of line (rare)
        return "QUESTION" in upper or "ANS" in upper or "SOL" in upper or "Q." in upper

    def _check_logical_transition(self, new_path: List[str], current_stack: List[str]) -> ValidationResult:
        """
        Strict hierarchy enforcement. 
        Deterministic rule: 
        - Main follows Main (or starts)
        - Alpha MUST follow Main (cannot start unless explicitly allowed)
        - Roman MUST follow Alpha (cannot directly follow Main)
        """
        main, alpha, roman = HierarchyUtils.decompose_path(new_path)
        c_main, c_alpha, c_roman = HierarchyUtils.decompose_path(current_stack)

        if not current_stack:
            # Paper start
            if main: return ValidationResult(True)
            if alpha == 'a': return ValidationResult(True) # Some starts with (a)
            return ValidationResult(False, "invalid starting numbering sequence")

        if main:
            # 1 -> 2 (ALLOWED)
            return ValidationResult(True)
        
        if alpha and not roman:
            # 1 -> (a) (ALLOWED)
            if not c_main:
                return ValidationResult(False, "alpha label found without parent main number")
            return ValidationResult(True)
            
        if roman:
            # 1 -> (a) -> (i) (ALLOWED)
            # 1 -> (i) (REJECTED by strict rule)
            if not c_alpha:
                return ValidationResult(False, "illegal hierarchy transition: roman must follow alpha")
            return ValidationResult(True)

        return ValidationResult(False, "unknown numbering pattern")
