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
        full_text: str
    ) -> ValidationResult:
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
            if not self.is_strong_header(raw_header):
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

    def is_strong_header(self, raw_header: str) -> bool:
        """
        Anchored word-boundary check for strong header keywords (QUESTION, ANSWER, SOL, etc.).
        """
        return bool(re.search(r"(?i)\b(?:QUESTION|ANSWER|ANS|SOL|SOLUTION|PART|SECTION)\b", raw_header))


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

        # Main level sequence check: prevent regression (e.g., question 2 appearing after question 13)
        if candidate_level == "main":
            c_main, _, _ = HierarchyUtils.decompose_path(current_stack)
            n_main, _, _ = HierarchyUtils.decompose_path(new_path)
            if c_main and n_main and c_main.isdigit() and n_main.isdigit():
                c_num = int(c_main)
                n_num = int(n_main)
                if n_num < c_num and (c_num - n_num) > 1:
                    return ValidationResult(False, f"out of order main question regression: {n_num} < {c_num}")

        return ValidationResult(True)


