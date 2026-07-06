import re
from .types import LayoutType, LayoutResult
from .extraction_patterns import ANSWER_SECTION_DELIMITERS, QUESTION_HEADER_PATTERNS, ANSWER_HEADER_PATTERNS

class DocumentLayoutDetector:
    """
    Decision tree to identify document layout: SECTION_WISE, INTERLEAVED, or UNKNOWN.
    """
    
from .types import LayoutType, LayoutResult, ParserConfig

class DocumentLayoutDetector:
    """
    Decision tree to identify document layout: SECTION_WISE, INTERLEAVED, or UNKNOWN.
    """
    
    def __init__(self, config: ParserConfig):
        self.config = config
        
    def detect_layout(self, text: str) -> LayoutResult:
        """
        Determines the layout based on structural signals.
        """
        # Step 1: Check for Section Delimiters
        for delim_regex in self.config.section_delimiters:
            delims = list(delim_regex.finditer(text))
            for delim in delims:
                pre_text = text[:delim.start()]
                post_text = text[delim.end():]
                
                # Check for questions before delimiter
                has_q_before = any(p.search(pre_text) for p in self.config.question_header_patterns)
                # Check for answers or more questions after delimiter
                has_a_after = any(p.search(post_text) for p in self.config.answer_header_patterns)
                has_q_after = any(p.search(post_text) for p in self.config.question_header_patterns)
                
                if has_q_before and (has_a_after or has_q_after):
                    return LayoutResult(
                        layout=LayoutType.SECTION_WISE,
                        boundary_position=delim.start(),
                        reason=f"Found section delimiter '{delim.group(0)}' with headers before and after."
                    )

        # Step 2: Check for INTERLEAVED pattern
        # We look for a few sequences of Q followed shortly by A
        q_regexes = self.config.question_header_patterns
        a_regexes = self.config.answer_header_patterns
        
        q_matches = []
        for r in q_regexes:
            q_matches.extend(list(r.finditer(text)))
        q_matches.sort(key=lambda x: x.start())
        
        a_matches = []
        for r in a_regexes:
            a_matches.extend(list(r.finditer(text)))
        a_matches.sort(key=lambda x: x.start())

        if q_matches and a_matches:
            alternating_sequences = 0
            # Look at first 15 questions to check for interleaved pattern
            for i in range(min(15, len(q_matches) - 1)):
                current_q = q_matches[i]
                next_q_pos = q_matches[i+1].start()
                
                # Is there an answer between this Q and the next Q?
                for a in a_matches:
                    if current_q.start() < a.start() < next_q_pos:
                        alternating_sequences += 1
                        break
            
            if alternating_sequences >= 3:
                return LayoutResult(
                    layout=LayoutType.INTERLEAVED,
                    reason=f"Detected {alternating_sequences} sequential Q->A blocks."
                )

        return LayoutResult(
            layout=LayoutType.UNKNOWN,
            reason="Insufficient structural evidence for SECTION_WISE or INTERLEAVED."
        )
