import re
import bisect
from typing import List, Optional, Dict, Any, Tuple
from .types import ParsedQuestion, QuestionLevel, ParserConfig, ParsingDiagnostics, QuestionParseResult
from .normalizer import Normalizer
from .header_validator import HeaderValidator
from .hierarchy_utils import HierarchyUtils

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
        # We also track the pattern index to resolve overlaps by pattern priority
        raw_matches = []
        for p_idx, regex in enumerate(self.config.question_header_patterns):
            for match in regex.finditer(text):
                raw_matches.append((match, p_idx))
        
        # Resolve overlapping matches: Keep the match with longer span or higher priority pattern
        raw_matches.sort(key=lambda x: x[0].start())
        resolved_matches: List[Tuple[re.Match, int]] = []
        
        for match, p_idx in raw_matches:
            is_valid_overlap = True
            matches_to_remove = []
            
            for j, (other_match, other_p_idx) in enumerate(resolved_matches):
                # Check for overlap
                if match.start() < other_match.end() and other_match.start() < match.end():
                    # Priority: 1. Longer match | 2. Higher pattern priority (lower p_idx)
                    match_len = match.end() - match.start()
                    other_len = other_match.end() - other_match.start()
                    
                    if match_len > other_len:
                        matches_to_remove.append(j)
                    elif match_len == other_len and p_idx < other_p_idx:
                        matches_to_remove.append(j)
                    else:
                        is_valid_overlap = False
                        break
            
            if is_valid_overlap:
                # Remove overlapping matches that this new match beats
                # We do it by index in reverse to avoid shifting
                for idx in sorted(matches_to_remove, reverse=True):
                    resolved_matches.pop(idx)
                resolved_matches.append((match, p_idx))
        
        all_potential_matches = sorted([m for m, _ in resolved_matches], key=lambda x: x.start())
        self.diagnostics = ParsingDiagnostics(total_matches=len(all_potential_matches))
        
        if not all_potential_matches:
            return []

        # Precompute page keys for true O(log n) lookup
        page_keys = [x[0] for x in page_offsets] if page_offsets else []

        parsed_questions = []
        hierarchy_stack: List[str] = []
        
        validated_matches = []
        for i, match in enumerate(all_potential_matches):
            raw_header = match.group(0)
            path = self.normalizer.normalize_header(raw_header)
            
            result = self.validator.is_valid(match, path, hierarchy_stack, text)
            if result.is_valid:
                # Update stack to get the full hierarchical path for this question
                HierarchyUtils.update_hierarchy_stack(hierarchy_stack, path)
                # Capture current stack state as the path for this question
                validated_matches.append((match, list(hierarchy_stack)))
            else:
                self.diagnostics.rejected_headers.append({
                    "header": raw_header, 
                    "reason": result.reason or "Unknown rejection"
                })

        self.diagnostics.validated_count = len(validated_matches)
        if not validated_matches:
            return []

        for i, (match, h_path) in enumerate(validated_matches):
            raw_header = match.group(0)
            start_offset = base_offset + match.start()
            
            next_match_start = validated_matches[i+1][0].start() if i + 1 < len(validated_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            block_text = text[match.end():next_match_start].strip()
            
            level = self._get_level(h_path)
            
            start_page = self._get_page_num_fast(match.start(), page_offsets, page_keys)
            end_page = self._get_page_num_fast(next_match_start - 1, page_offsets, page_keys)
            
            parsed_questions.append(ParsedQuestion(
                hierarchy_path=h_path,
                raw_header=raw_header,
                text=block_text,
                start_offset=start_offset,
                end_offset=end_offset,
                start_page=start_page,
                end_page=end_page,
                level=level
            ))
            
        return parsed_questions

    def parse_with_diagnostics(
        self,
        text: str,
        page_offsets: List[Tuple[int, int]],
        base_offset: int = 0,
    ) -> QuestionParseResult:
        """
        Same as parse() but returns a QuestionParseResult that bundles the
        questions list with the diagnostics from this run.  Prefer this method
        when the caller needs to inspect rejected headers or match counts
        without accessing mutable parser instance state.
        """
        questions = self.parse(text, page_offsets, base_offset)
        return QuestionParseResult(questions=questions, diagnostics=self.diagnostics)

    def _get_level(self, path: List[str]) -> QuestionLevel:
        if len(path) >= 3: return QuestionLevel.SUB_SUB
        if len(path) == 2: return QuestionLevel.SUB
        return QuestionLevel.MAIN

    def _get_page_num_fast(self, offset: int, page_offsets: List[Tuple[int, int]], page_keys: List[int]) -> int:
        """
        Finds the page number for a given character offset using binary search on precomputed keys.
        """
        if not page_keys: return 1
        idx = bisect.bisect_right(page_keys, offset) - 1
        return page_offsets[max(0, idx)][1]
