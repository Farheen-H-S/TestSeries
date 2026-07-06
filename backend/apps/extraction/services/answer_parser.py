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
    
    def __init__(self, config: ParserConfig = None):
        patterns = config.answer_header_patterns if config else ANSWER_HEADER_PATTERNS
        self.regex = re.compile("|".join(patterns), re.IGNORECASE | re.MULTILINE)
        self.normalizer = Normalizer()

    def parse(self, text: str, page_offsets: List[Tuple[int, int]]) -> List[ParsedAnswer]:
        """
        Parses text into a list of answers with stateful path resolution.
        """
        matches = list(self.regex.finditer(text))
        if not matches:
            return []

        parsed_answers = []
        
        # Stateful tracking
        current_main: int = 0
        current_alpha: Optional[str] = None
        
        for i, match in enumerate(matches):
            raw_header = match.group(0)
            start_offset = match.start()
            end_offset = matches[i+1].start() if i + 1 < len(matches) else len(text)
            
            block_text = text[match.end():end_offset].strip()
            
            # Extract from current header
            main, alpha, roman = self.normalizer.normalize_header(raw_header)
            
            # Resolve Hierarchy
            if main > 0:
                current_main = main
                current_alpha = alpha
            elif alpha:
                current_alpha = alpha
            elif roman:
                pass
            
            # Construct path
            path = []
            if current_main > 0:
                path.append(str(current_main))
                if current_alpha:
                    path.append(current_alpha)
                    if roman:
                        path.append(roman)
                elif roman:
                    path.append(roman)
            else:
                path = self.normalizer.get_hierarchy_path(main, alpha, roman)
            
            start_page = self._get_page_num(start_offset, page_offsets)
            end_page = self._get_page_num(end_offset - 1, page_offsets)
            
            parsed_answers.append(ParsedAnswer(
                hierarchy_path=path,
                raw_header=raw_header,
                text=block_text,
                start_offset=start_offset,
                end_offset=end_offset,
                start_page=start_page,
                end_page=end_page
            ))
            
        return parsed_answers

    def _get_page_num(self, offset: int, page_offsets: List[Tuple[int, int]]) -> int:
        for i in range(len(page_offsets) - 1):
            if page_offsets[i][0] <= offset < page_offsets[i+1][0]:
                return page_offsets[i][1]
        return page_offsets[-1][1] if page_offsets else 1
