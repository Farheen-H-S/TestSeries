import re
from typing import List, Tuple
from .types import ParsedAnswer, ParserConfig
from .normalizer import Normalizer
from .extraction_patterns import ANSWER_HEADER_PATTERNS

class AnswerParser:
    """
    Greedy parser for extracting answer blocks.
    In SECTION_WISE documents, it can also be driven by numbering patterns.
    """
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.normalizer = Normalizer()

    def parse(self, text: str, page_offsets: List[Tuple[int, int]], base_offset: int = 0) -> List[ParsedAnswer]:
        """
        Parses text into a list of answers with stateful path resolution and absolute offsets.
        """
        all_potential_matches = []
        for regex in self.config.answer_header_patterns:
            all_potential_matches.extend(list(regex.finditer(text)))
        all_potential_matches.sort(key=lambda x: x.start())

        if not all_potential_matches:
            return []

        parsed_answers = []
        
        # Stateful tracking
        hierarchy_stack: List[str] = []
        
        for i, match in enumerate(all_potential_matches):
            raw_header = match.group(0)
            # Absolute offsets
            start_offset = base_offset + match.start()
            
            next_match_start = all_potential_matches[i+1].start() if i + 1 < len(all_potential_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            block_text = text[match.end():next_match_start].strip()
            
            # Extract from current header
            path = self.normalizer.normalize_header(raw_header)
            self._update_hierarchy_stack(hierarchy_stack, path)
            
            start_page = self._get_page_num(start_offset, page_offsets)
            end_page = self._get_page_num(end_offset - 1, page_offsets)
            
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
        
        main = new_path[0] if new_path[0].isdigit() else None
        alpha = None
        roman = None
        for p in new_path:
            if p.isdigit(): main = p
            elif len(p) == 1 and p.isalpha(): alpha = p
            else: roman = p

        if main:
            stack.clear()
            stack.append(main)
            if alpha: stack.append(alpha)
            if roman: stack.append(roman)
        elif alpha:
            while len(stack) > 1: stack.pop()
            stack.append(alpha)
        elif roman:
            while len(stack) > 2: stack.pop()
            stack.append(roman)

    def _get_page_num(self, offset: int, page_offsets: List[Tuple[int, int]]) -> int:
        """
        Finds the page number for a given relative character offset within the slice.
        """
        for i in range(len(page_offsets) - 1):
            if page_offsets[i][0] <= offset < page_offsets[i+1][0]:
                return page_offsets[i][1]
        return page_offsets[-1][1] if page_offsets else 1
