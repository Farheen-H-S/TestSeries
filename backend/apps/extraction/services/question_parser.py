import re
import bisect
from typing import List, Optional, Dict, Any, Tuple
from .types import ParsedQuestion, QuestionLevel, ParserConfig, ParsingDiagnostics
from .normalizer import Normalizer
from .header_validator import HeaderValidator

class QuestionParser:
    """
    Greedy, hierarchy-aware parser for extracting question blocks.
    Delegates validation to HeaderValidator and uses binary search for performance.
    """
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.normalizer = Normalizer()
        self.validator = HeaderValidator()
        self.diagnostics = ParsingDiagnostics()

    def parse(self, text: str, page_offsets: List[Tuple[int, int]], base_offset: int = 0) -> List[ParsedQuestion]:
        """
        Parses text into a list of hierarchical questions with strict validation and offset correction.
        """
        # Collect all potential matches from all patterns
        raw_matches = []
        for regex in self.config.question_header_patterns:
            raw_matches.extend(list(regex.finditer(text)))
        
        # Deduplicate matches by span (start, end)
        unique_matches = {}
        for m in raw_matches:
            span = (m.start(), m.end())
            if span not in unique_matches:
                unique_matches[span] = m
        
        all_potential_matches = sorted(unique_matches.values(), key=lambda x: x.start())
        self.diagnostics = ParsingDiagnostics(total_matches=len(all_potential_matches))
        
        if not all_potential_matches:
            return []

        parsed_questions = []
        hierarchy_stack: List[str] = []
        
        validated_matches = []
        for i, match in enumerate(all_potential_matches):
            raw_header = match.group(0)
            path = self.normalizer.normalize_header(raw_header)
            
            # Simple rejection check (should have path)
            if not path:
                self.diagnostics.rejected_headers.append({"header": raw_header, "reason": "No valid identifier found"})
                continue

            if self.validator.is_valid(match, path, hierarchy_stack, text):
                # Update stack to get the full hierarchical path for this question
                self._update_hierarchy_stack(hierarchy_stack, path)
                # Capture current stack state as the path for this question
                validated_matches.append((match, list(hierarchy_stack)))
            else:
                self.diagnostics.rejected_headers.append({"header": raw_header, "reason": "Structural or hierarchy rejection"})

        self.diagnostics.validated_count = len(validated_matches)
        if not validated_matches:
            return []

        for i, (match, path) in enumerate(validated_matches):
            raw_header = match.group(0)
            start_offset = base_offset + match.start()
            
            next_match_start = validated_matches[i+1][0].start() if i + 1 < len(validated_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            block_text = text[match.end():next_match_start].strip()
            
            # Use the augmented path from the stack state
            level = self._get_level(path)
            
            # Use binary search for page lookup
            start_page = self._get_page_num_fast(match.start(), page_offsets)
            end_page = self._get_page_num_fast(next_match_start - 1, page_offsets)
            
            parsed_questions.append(ParsedQuestion(
                hierarchy_path=path,
                raw_header=raw_header,
                text=block_text,
                start_offset=start_offset,
                end_offset=end_offset,
                start_page=start_page,
                end_page=end_page,
                level=level
            ))
            
        return parsed_questions

    def _get_level(self, path: List[str]) -> QuestionLevel:
        if len(path) >= 3: return QuestionLevel.SUB_SUB
        if len(path) == 2: return QuestionLevel.SUB
        return QuestionLevel.MAIN

    def _update_hierarchy_stack(self, stack: List[str], new_path: List[str]):
        """
        Updates the stateful stack based on the new path.
        """
        if not new_path: return

        main, alpha, roman = self.validator._decompose_path(new_path)

        if main:
            stack.clear()
            stack.append(main)
            if alpha: stack.append(alpha)
            if roman: stack.append(roman)
        elif alpha:
            while len(stack) > 1: stack.pop()
            stack.append(alpha)
            if roman: stack.append(roman)
        elif roman:
            while len(stack) > 2: stack.pop()
            stack.append(roman)

    def _get_page_num_fast(self, offset: int, page_offsets: List[Tuple[int, int]]) -> int:
        """
        Finds the page number for a given character offset using binary search.
        """
        if not page_offsets: return 1
        # Extract offsets for bisect
        keys = [x[0] for x in page_offsets]
        idx = bisect.bisect_right(keys, offset) - 1
        return page_offsets[max(0, idx)][1]

