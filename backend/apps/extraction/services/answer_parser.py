import re
import logging
from typing import List, Tuple, Optional
from .types import ParsedAnswer, ParserConfig, AnswerParseResult, ParsingDiagnostics
from .normalizer import Normalizer
from .hierarchy_utils import HierarchyUtils

logger = logging.getLogger(__name__)


class AnswerParser:
    """
    Greedy parser for extracting answer blocks.
    Deduplicates matches and uses binary search for performance.
    """
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.normalizer = Normalizer()
        self.diagnostics = ParsingDiagnostics()

    def parse(self, text: str, page_offsets: List[Tuple[int, int]], base_offset: int = 0) -> List[ParsedAnswer]:
        """
        Parses text into a list of answers with stateful path resolution and absolute offsets.
        """
        try:
            result = self.parse_with_diagnostics(text, page_offsets, base_offset)
            self.diagnostics = result.diagnostics
            return result.answers
        except Exception as e:
            logger.error("Answer parser failure: %s", str(e), exc_info=True)
            raise


    def parse_with_diagnostics(
        self,
        text: str,
        page_offsets: List[Tuple[int, int]],
        base_offset: int = 0,
    ) -> AnswerParseResult:
        """
        Parses text and returns an AnswerParseResult that bundles the
        answers list with the diagnostics from this run.
        """
        # Pre-normalize the text for OCR errors before matching
        normalized_text = self.normalizer.pre_normalize_ocr(text)

        # Collect all potential matches from all patterns using the normalized text
        raw_matches = []
        for p_idx, regex in enumerate(self.config.answer_header_patterns):
            for match in regex.finditer(normalized_text):
                raw_matches.append((match, p_idx))
            
        # Resolve overlapping matches: Sort by start index ascending, length descending, and pattern priority ascending
        raw_matches.sort(key=lambda x: (x[0].start(), -x[0].end(), x[1]))
        resolved_matches: List[Tuple[re.Match, int]] = []

        for match, p_idx in raw_matches:
            is_accepted = True
            to_remove = []

            for j, (other_match, other_p_idx) in enumerate(resolved_matches):
                if match.start() < other_match.end() and other_match.start() < match.end():
                    # Overlapping: compare by length then pattern priority
                    match_len = match.end() - match.start()
                    other_len = other_match.end() - other_match.start()
                    if match_len > other_len or (match_len == other_len and p_idx < other_p_idx):
                        to_remove.append(j)
                    else:
                        is_accepted = False
                        break

            if is_accepted:
                for idx in sorted(to_remove, reverse=True):
                    resolved_matches.pop(idx)
                resolved_matches.append((match, p_idx))

        all_potential_matches = sorted([m for m, _ in resolved_matches], key=lambda x: x.start())
        diagnostics = ParsingDiagnostics(total_matches=len(all_potential_matches))

        if not all_potential_matches:
            return AnswerParseResult(answers=[], diagnostics=diagnostics)

        # Precompute page keys for true O(log n) lookup
        page_keys = [x[0] for x in page_offsets] if page_offsets else []

        parsed_answers = []
        hierarchy_stack: List[str] = []
        
        for i, match in enumerate(all_potential_matches):
            normalized_header = match.group(0)
            raw_header = text[match.start():match.end()]
            start_offset = base_offset + match.start()
            
            next_match_start = all_potential_matches[i+1].start() if i + 1 < len(all_potential_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            block_text = text[match.end():next_match_start].strip()
            
            path = self.normalizer.normalize_header(normalized_header)
            # Use shared hierarchy logic
            old_stack = list(hierarchy_stack)
            HierarchyUtils.update_hierarchy_stack(hierarchy_stack, path)
            logger.debug(
                "Hierarchy stack transition (Answer) | old_stack=%s | new_stack=%s | header=%s | start_offset=%d",
                old_stack, hierarchy_stack, normalized_header, match.start()
            )
            
            # Use centralized O(log n) page lookup from HierarchyUtils
            start_page = HierarchyUtils.get_page_num_fast(start_offset, page_offsets, page_keys)
            end_page = HierarchyUtils.get_page_num_fast(end_offset - 1, page_offsets, page_keys)
            
            parsed_answers.append(ParsedAnswer(
                hierarchy_path=list(hierarchy_stack),
                raw_header=raw_header,
                text=block_text,
                start_offset=start_offset,
                end_offset=end_offset,
                start_page=start_page,
                end_page=end_page
            ))
            
        diagnostics.validated_count = len(parsed_answers)
        return AnswerParseResult(answers=parsed_answers, diagnostics=diagnostics)

