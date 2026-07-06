import re
from typing import List, Optional, Dict, Any
from .types import ParsedQuestion, QuestionLevel, ParserConfig
from .normalizer import Normalizer
from .extraction_patterns import QUESTION_HEADER_PATTERNS

class QuestionParser:
    """
    Greedy, hierarchy-aware parser for extracting question blocks.
    """
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.normalizer = Normalizer()

    def parse(self, text: str, page_offsets: List[Tuple[int, int]], base_offset: int = 0) -> List[ParsedQuestion]:
        """
        Parses text into a list of hierarchical questions with strict validation and offset correction.
        """
        # Collect all potential matches from all patterns
        all_potential_matches = []
        for regex in self.config.question_header_patterns:
            all_potential_matches.extend(list(regex.finditer(text)))
        
        # Sort by occurrence
        all_potential_matches.sort(key=lambda x: x.start())
        
        if not all_potential_matches:
            return []

        parsed_questions = []
        
        # Hierarchy Stack: List of (level_name, raw_value)
        # Example: [("MAIN", "1"), ("SUB", "a"), ("SUB_SUB", "i")]
        hierarchy_stack: List[str] = []
        
        # We need a way to validate each match before accepting it
        validated_matches = []
        for i, match in enumerate(all_potential_matches):
            raw_header = match.group(0)
            path = self.normalizer.normalize_header(raw_header)
            
            if self._is_valid_header(match, path, hierarchy_stack, text):
                validated_matches.append((match, path))
                # Update hierarchy stack for the NEXT validation
                self._update_hierarchy_stack(hierarchy_stack, path)

        if not validated_matches:
            return []

        for i, (match, path) in enumerate(validated_matches):
            raw_header = match.group(0)
            # Absolute offsets in the original document
            start_offset = base_offset + match.start()
            
            next_match_start = validated_matches[i+1][0].start() if i + 1 < len(validated_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            block_text = text[match.end():next_match_start].strip()
            
            # Determine Level
            if len(path) == 3:
                level = QuestionLevel.SUB_SUB
            elif len(path) == 2:
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

    def _is_valid_header(self, match, path, current_stack, full_text) -> bool:
        """
        Structural validation of a potential header.
        """
        if not path:
            return False
            
        raw_header = match.group(0)
        
        # 1. Rule: Must be at start of line (allowing some whitespace)
        # Check the characters before the match
        start_idx = match.start()
        if start_idx > 0:
            pre_chars = full_text[max(0, start_idx-2):start_idx]
            if "\n" not in pre_chars and start_idx > 2:
                # Not at start of line
                # Strong headers like "Question 1" might still be valid if it's the first thing on a page
                if not ("QUESTION" in raw_header.upper() or "Q." in raw_header.upper()):
                    return False

        # 2. Sequence Rule: If it's a simple number, is it the next in sequence?
        # If stack is empty, it should be "1" (or similar)
        # If stack top is main="1", next main should be "2"
        # Since OCR can skip numbers, we are lenient but we avoid "1." inside a paragraph.
        
        # If it's a "weak" pattern (just a number), require it to be at start of line.
        is_weak = not ("QUESTION" in raw_header.upper() or "Q." in raw_header.upper())
        if is_weak:
            # Check if it was preceded by a newline
            if start_idx > 0 and full_text[start_idx-1] not in ("\n", "\r", "\f"):
                return False

        return True

    def _update_hierarchy_stack(self, stack: List[str], new_path: List[str]):
        """
        Updates the stateful stack based on the new path.
        """
        # If new_path is [1], stack becomes [1]
        # If new_path is [1, a], stack becomes [1, a]
        # If new_path is [a] and stack was [1], stack becomes [1, a]
        # If new_path is [i] and stack was [1, a], stack becomes [1, a, i]
        
        if not new_path:
            return

        # Tokenized components
        main = new_path[0] if new_path[0].isdigit() else None
        alpha = None
        roman = None
        
        # Determine if it's alphanumeric or roman
        for p in new_path:
            if p.isdigit(): main = p
            elif len(p) == 1 and p.isalpha(): alpha = p
            else: roman = p # Simplified

        if main:
            stack.clear()
            stack.append(main)
            if alpha: stack.append(alpha)
            if roman: stack.append(roman)
        elif alpha:
            # Sub-question: pop until we reach MAIN
            while len(stack) > 1:
                stack.pop()
            stack.append(alpha)
        elif roman:
            # Sub-sub-question: pop until we reach ALPHA
            while len(stack) > 2:
                stack.pop()
            stack.append(roman)

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
