import re
from typing import List, Optional
from .extraction_patterns import INSTRUCTION_PRIORITY

class InstructionDetector:
    """
    Priority-based instruction verb detector.
    """
    
    def __init__(self, priority_list: List[str] = None):
        self.priority_list = [v.upper() for v in (priority_list or INSTRUCTION_PRIORITY)]

    def detect(self, text: str) -> Optional[str]:
        """
        Returns the highest priority instruction verb found in the text.
        """
        upper_text = text.upper()
        
        for verb in self.priority_list:
            if re.search(rf"\b{re.escape(verb)}\b", upper_text):
                return verb
                
        return None
