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
    
    def is_valid(
        self,
        match: re.Match,
        path: List[str],
        current_stack: List[str],
        full_text: str,
        inside_working_notes: bool = False
    ) -> ValidationResult:
        """
        Validates if a potential header is structurally sound and logically follows the current hierarchy.
        Returns ValidationResult with a detailed reason for rejection.
        """
        if not path:
            return ValidationResult(False, "failed OCR normalization / no identifier found")
            
        raw_header = match.group(0)
        start_idx = match.start()

        # 0. Working Notes Zone Validation
        if inside_working_notes:
            from .extraction_patterns import WORKING_NOTE_HEADER_PATTERNS
            if any(re.search(pat, raw_header) for pat in WORKING_NOTE_HEADER_PATTERNS):
                return ValidationResult(False, "explicit Working Note header")
                
            is_strong = self._is_strong_header(raw_header)
            
            c_main, _, _ = HierarchyUtils.decompose_path(path)
            s_main, _, _ = HierarchyUtils.decompose_path(current_stack)
            
            c_num = int(c_main) if c_main and c_main.isdigit() else 0
            s_num = int(s_main) if s_main and s_main.isdigit() else 0
            
            # Non-strong headers with numbers <= current stack main number belong to working notes
            if not is_strong and (c_num == 0 or c_num <= s_num):
                return ValidationResult(False, "item inside Working Notes section")
            
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
            if char in ('\n', '\r'):
                return True
            if char not in (' ', '\t'):
                return False
            check_idx -= 1
        return True

    def _is_strong_header(self, raw_header: str) -> bool:
        upper = raw_header.upper()
        # Strong markers that can appear without being at start of line (rare)
        return "QUESTION" in upper or "ANS" in upper or "SOL" in upper or "Q." in upper

    ALLOWED_PARENT_LEVELS = {
        "main": {"root", "main", "alpha", "roman"},
        "alpha": {"root", "main", "alpha", "roman"},
        "roman": {"main", "alpha", "roman"}
    }

    def _get_candidate_level(self, path: List[str]) -> Optional[str]:
        main, alpha, roman = HierarchyUtils.decompose_path(path)
        if main:
            return "main"
        if alpha:
            return "alpha"
        if roman:
            return "roman"
        return None

    def _get_stack_level(self, path: List[str]) -> Optional[str]:
        main, alpha, roman = HierarchyUtils.decompose_path(path)
        if roman:
            return "roman"
        if alpha:
            return "alpha"
        if main:
            return "main"
        return None

    def _check_logical_transition(self, new_path: List[str], current_stack: List[str]) -> ValidationResult:
        """
        Transition Grammar Validation.
        Determines valid Parent -> Child transitions using a structural allowed level table.
        """
        candidate_level = self._get_candidate_level(new_path)
        if not candidate_level:
            return ValidationResult(False, "unknown numbering pattern")

        if not current_stack:
            # Paper start rules
            if candidate_level == "main":
                return ValidationResult(True)
            if candidate_level == "alpha":
                # Only allow starting with 'a' or 'A'
                main, alpha, roman = HierarchyUtils.decompose_path(new_path)
                if alpha == 'a':
                    return ValidationResult(True)
                return ValidationResult(False, "invalid starting numbering sequence")
            return ValidationResult(False, "invalid starting numbering sequence")

        current_level = self._get_stack_level(current_stack)
        if not current_level:
            current_level = "root"

        allowed_parents = self.ALLOWED_PARENT_LEVELS.get(candidate_level, set())
        if current_level not in allowed_parents:
            return ValidationResult(
                False,
                f"illegal hierarchy transition: candidate level '{candidate_level}' cannot follow current level '{current_level}'"
            )

        # Context constraints: alpha must have a parent main number unless it's a mainless stack
        if candidate_level == "alpha":
            c_main, c_alpha, c_roman = HierarchyUtils.decompose_path(current_stack)
            if not c_main and not c_alpha:
                return ValidationResult(False, "alpha label found without parent main number")

        return ValidationResult(True)


