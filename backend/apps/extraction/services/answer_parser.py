import re
import bisect
from typing import List, Tuple, Optional
from .types import ParsedAnswer, ParserConfig
from .normalizer import Normalizer

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
        raw_matches = []
        for regex in self.config.answer_header_patterns:
            raw_matches.extend(list(regex.finditer(text)))
            
        unique_matches = {}
        for m in raw_matches:
            span = (m.start(), m.end())
            if span not in unique_matches:
                unique_matches[span] = m
                
        all_potential_matches = sorted(unique_matches.values(), key=lambda x: x.start())

        if not all_potential_matches:
            return []

        parsed_answers = []
        hierarchy_stack: List[str] = []
        
        for i, match in enumerate(all_potential_matches):
            raw_header = match.group(0)
            start_offset = base_offset + match.start()
            
            next_match_start = all_potential_matches[i+1].start() if i + 1 < len(all_potential_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            block_text = text[match.end():next_match_start].strip()
            
            path = self.normalizer.normalize_header(raw_header)
            self._update_hierarchy_stack(hierarchy_stack, path)
            
            start_page = self._get_page_num_fast(match.start(), page_offsets)
            end_page = self._get_page_num_fast(next_match_start - 1, page_offsets)
            
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

    def _update_hierarchy_stack(self, stack: List[str], new_path: List[str]):
        if not new_path: return
        
        # We reuse the logic from question parser via decomposition if possible,
        # but answers are often simpler.
        main = new_path[0] if new_path[0].isdigit() else None
        alpha = None
        roman = None
        
        # Explicit Roman check for consistency
        ROMAN_REGEX = re.compile(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv)$', re.IGNORECASE)
        
        for p in new_path:
            if p.isdigit(): main = p
            elif ROMAN_REGEX.match(p): roman = p
            elif len(p) == 1 and p.isalpha(): alpha = p

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
        if not page_offsets: return 1
        keys = [x[0] for x in page_offsets]
        idx = bisect.bisect_right(keys, offset) - 1
        return page_offsets[max(0, idx)][1]
