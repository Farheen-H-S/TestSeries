import re
from .types import LayoutType, LayoutResult
from .extraction_patterns import ANSWER_SECTION_DELIMITERS, QUESTION_HEADER_PATTERNS, ANSWER_HEADER_PATTERNS

class DocumentLayoutDetector:
    """
    Decision tree to identify document layout: SECTION_WISE, INTERLEAVED, or UNKNOWN.
    """
    
    def __init__(self, delimiters=None, q_patterns=None, a_patterns=None):
        self.delimiters = delimiters or ANSWER_SECTION_DELIMITERS
        self.q_patterns = q_patterns or QUESTION_HEADER_PATTERNS
        self.a_patterns = a_patterns or ANSWER_HEADER_PATTERNS
        
        # Compile patterns
        self.delimiter_regex = re.compile("|".join(self.delimiters), re.IGNORECASE | re.MULTILINE)
        self.q_regex = re.compile("|".join(self.q_patterns), re.IGNORECASE | re.MULTILINE)
        self.a_regex = re.compile("|".join(self.a_patterns), re.IGNORECASE | re.MULTILINE)

    def detect_layout(self, text: str) -> LayoutResult:
        """
        Determines the layout based on structural signals.
        """
        # Step 1: Check for Section Delimiters
        delimiter_match = self.delimiter_regex.search(text)
        if delimiter_match:
            # Signal: Found clear answer section header.
            # Check if headers appear after it
            post_text = text[delimiter_match.end():]
            if self.q_regex.search(post_text) or self.a_regex.search(post_text):
                return LayoutResult(
                    layout=LayoutType.SECTION_WISE,
                    boundary_position=delimiter_match.start(),
                    reason=f"Found section delimiter '{delimiter_match.group(0)}' with headers following."
                )

        # Step 2: Check for INTERLEAVED pattern
        # Look for repeated Q -> A pattern
        # We search first 50% of the doc for efficiency or just the whole doc? 
        # ICAI docs are large, let's look for a few sequences.
        q_matches = list(self.q_regex.finditer(text))
        a_matches = list(self.a_regex.finditer(text))
        
        # If we find alternating Q and A headers multiple times
        alternating_count = 0
        if q_matches and a_matches:
            # Very simple check: are there multiple Answer headers interspersed with Question headers?
            # A more robust check could look at the offsets.
            last_a_pos = -1
            for q in q_matches[:10]: # Check first few questions
                # Find if an Answer follows this Question before the next Question
                for a in a_matches:
                    if a.start() > q.start():
                        # Found an answer after a question
                        alternating_count += 1
                        break
            
            if alternating_count >= 3:
                return LayoutResult(
                    layout=LayoutType.INTERLEAVED,
                    reason=f"Detected {alternating_count} alternating Question/Answer headers."
                )

        return LayoutResult(
            layout=LayoutType.UNKNOWN,
            reason="No clear section delimiter or interleaved pattern detected."
        )
