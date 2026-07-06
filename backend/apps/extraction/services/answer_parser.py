import re
import bisect
from typing import List, Tuple, Optional
from .types import ParsedAnswer, ParserConfig
from .normalizer import Normalizer
from .hierarchy_utils import HierarchyUtils

class AnswerParser:
    """
    Greedy parser for extracting answer blocks.
    Deduplicates matches and uses binary search for performance.
    """
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.normalizer = Normalizer()

    def parse(self, text: str, page_offsets: List[Tuple[int, int]], base_offset: int = 0) -> List[ParsedAnswer]:
        """
        Parses text into a list of answers with stateful path resolution and absolute offsets.
        """
        # Collect all potential matches from all patterns
        raw_matches = []
        for p_idx, regex in enumerate(self.config.answer_header_patterns):
            for match in regex.finditer(text):
                raw_matches.append((match, p_idx))
            
        # Resolve overlapping matches: prefer longer span; break ties by lower pattern index (higher priority).
        # Same deterministic algorithm used by QuestionParser.
        raw_matches.sort(key=lambda x: x[0].start())
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


        if not all_potential_matches:
            return []

        # Precompute page keys for true O(log n) lookup
        page_keys = [x[0] for x in page_offsets] if page_offsets else []

        parsed_answers = []
        hierarchy_stack: List[str] = []
        
        for i, match in enumerate(all_potential_matches):
            raw_header = match.group(0)
            start_offset = base_offset + match.start()
            
            next_match_start = all_potential_matches[i+1].start() if i + 1 < len(all_potential_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            block_text = text[match.end():next_match_start].strip()
            
            path = self.normalizer.normalize_header(raw_header)
            # Use shared hierarchy logic
            HierarchyUtils.update_hierarchy_stack(hierarchy_stack, path)
            
            start_page = self._get_page_num_fast(match.start(), page_offsets, page_keys)
            end_page = self._get_page_num_fast(next_match_start - 1, page_offsets, page_keys)
            
            parsed_answers.append(ParsedAnswer(
                hierarchy_path=list(hierarchy_stack),
                raw_header=raw_header,
                text=block_text,
                start_offset=start_offset,
                end_offset=end_offset,
                start_page=start_page,
                end_page=end_page
            ))
            
        return parsed_answers

    def _get_page_num_fast(self, offset: int, page_offsets: List[Tuple[int, int]], page_keys: List[int]) -> int:
        """
        Finds the page number for a given character offset using binary search on precomputed keys.
        """
        if not page_keys: return 1
        idx = bisect.bisect_right(page_keys, offset) - 1
        return page_offsets[max(0, idx)][1]
