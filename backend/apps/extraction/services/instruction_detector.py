import re
from typing import List, Optional, Tuple
from .extraction_patterns import INSTRUCTION_PRIORITY

class InstructionDetector:
    """
    Priority-based instruction verb detector.
    """
    
    def __init__(self, priority_list: List[str] = None):
        verbs = [v.upper() for v in (priority_list or INSTRUCTION_PRIORITY)]
        self.patterns: List[Tuple[str, re.Pattern]] = []
        for verb in verbs:
            # Robust word boundaries (including trailing punctuation support)
            start_boundary = r"\b" if verb[0].isalnum() or verb[0] == '_' else ""
            end_boundary = r"\b" if verb[-1].isalnum() or verb[-1] == '_' else r"(?!\w)"
            pattern_str = f"{start_boundary}{re.escape(verb)}{end_boundary}"
            self.patterns.append((verb, re.compile(pattern_str)))

    def detect(self, text: str) -> Optional[str]:
        """
        Returns the highest priority instruction verb found in the text.
        """
        upper_text = text.upper()
        
        for verb, pattern in self.patterns:
            if pattern.search(upper_text):
                return verb
                
        return None
