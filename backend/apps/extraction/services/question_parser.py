import re
from typing import List, Optional, Dict, Any
from .types import ParsedQuestion, QuestionLevel, ParserConfig
from .normalizer import Normalizer
from .extraction_patterns import QUESTION_HEADER_PATTERNS

class QuestionParser:
    """
    Greedy, hierarchy-aware parser for extracting question blocks.
    """
    
    def __init__(self, config: ParserConfig = None):
        patterns = config.question_header_patterns if config else QUESTION_HEADER_PATTERNS
        self.regex = re.compile("|".join(patterns), re.IGNORECASE | re.MULTILINE)
        self.normalizer = Normalizer()

    def parse(self, text: str, page_offsets: List[Tuple[int, int]]) -> List[ParsedQuestion]:
        """
        Parses text into a list of hierarchical questions with stateful path resolution.
        """
        matches = list(self.regex.finditer(text))
        if not matches:
            return []

        parsed_questions = []
        
        # Stateful tracking of current main, secondary, and tertiary levels
        current_main: int = 0
        current_alpha: Optional[str] = None
        
        for i, match in enumerate(matches):
            raw_header = match.group(0)
            start_offset = match.start()
            end_offset = matches[i+1].start() if i + 1 < len(matches) else len(text)
            
            block_text = text[match.end():end_offset].strip()
            
            # Extract identifiers from the current header
            main, alpha, roman = self.normalizer.normalize_header(raw_header)
            
            # Resolve Hierarchy
            if main > 0:
                # This is a new main question or a hybrid header like 1(a)
                current_main = main
                current_alpha = alpha # Might be None if just "1." or string "a" if "1(a)"
            elif alpha:
                # This is a sub-question like (a). It belongs to the last seen current_main.
                current_alpha = alpha
            elif roman:
                # This is a sub-sub-question like (i). 
                # It belongs to current_main and current_alpha.
                pass 
            
            # Construct hierarchy path based on state
            path = []
            if current_main > 0:
                path.append(str(current_main))
                if current_alpha:
                    path.append(current_alpha)
                    if roman:
                        path.append(roman)
                elif roman:
                    # Case: Question 1 -> (i). Rare but possible.
                    path.append(roman)
            else:
                # Fallback for orphaned headers at start of doc
                path = self.normalizer.get_hierarchy_path(main, alpha, roman)

            # Determine Level
            if roman:
                level = QuestionLevel.SUB_SUB
            elif alpha:
                level = QuestionLevel.SUB
            else:
                level = QuestionLevel.MAIN
                
            start_page = self._get_page_num(start_offset, page_offsets)
            end_page = self._get_page_num(end_offset - 1, page_offsets)
            
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

    def _get_page_num(self, offset: int, page_offsets: List[Tuple[int, int]]) -> int:
        """
        Finds the page number for a given character offset.
        """
        for i in range(len(page_offsets) - 1):
            if page_offsets[i][0] <= offset < page_offsets[i+1][0]:
                return page_offsets[i][1]
        return page_offsets[-1][1] if page_offsets else 1

# Maintain backward compatibility for extraction_pipeline until updated
def parse_questions(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # This is a temporary wrapper to avoid breaking current code during incremental implementation
    full_text = ""
    # We ignore the actual page-by-page parsing of old parser and join text
    offset = 0
    offsets = []
    for p in pages:
        offsets.append((offset, p["page_number"]))
        full_text += p["text"] + "\n"
        offset += len(p["text"]) + 1
        
    parser = QuestionParser()
    parsed = parser.parse(full_text, offsets)
    
    # Convert to format expected by old pipeline
    return [
        {
            "question_number": ".".join(q.hierarchy_path),
            "question_text": q.text,
            "source_page": q.start_page
        }
        for q in parsed
    ]
