import re
from typing import List, Tuple, Optional

class Normalizer:
    """
    Standardizes headers and handles deterministic OCR corrections.
    """
    
    @staticmethod
    def ocr_correct(text: str) -> str:
        """
        Applies deterministic OCR correction for common mistakes in numeric contexts.
        """
        if not text:
            return ""
            
        # Common OCR mistakes: l/I/| for 1, O for 0
        # We only apply these if the resulting string is clearly numeric or a common label
        
        # 1. Handle isolated l, I, | -> 1
        text = re.sub(r'\b[lI|]\b', '1', text)
        
        # 2. Handle O -> 0 in numeric context (e.g., Q.1O -> Q.10)
        # Only if O is surrounded by digits or start/end of string
        text = re.sub(r'(?<=\d)O|O(?=\d)', '0', text)
        
        return text

    @staticmethod
    def normalize_header(raw_header: str) -> Tuple[int, Optional[str], Optional[str]]:
        """
        Converts a raw header into a canonical (number, label, sub_label) tuple.
        Examples:
        "Question 1(a)(i)" -> (1, "a", "i")
        "1." -> (1, None, None)
        """
        # First OCR correct
        header = Normalizer.ocr_correct(raw_header.strip())
        
        # Greedy extraction of digits for the main number
        num_match = re.search(r'(\d+)', header)
        main_number = int(num_match.group(1)) if num_match else 0
        
        # Extract alpha label (a), (b)
        alpha_match = re.search(r'\(([a-z])\)', header, re.IGNORECASE)
        alpha_label = alpha_match.group(1).lower() if alpha_match else None
        
        # Extract roman label (i), (ii)
        roman_match = re.search(r'\(([ivxIVX]+)\)', header)
        roman_label = roman_match.group(1).lower() if roman_match else None
        
        return main_number, alpha_label, roman_label

    @staticmethod
    def get_hierarchy_path(main_number: int, alpha_label: Optional[str] = None, roman_label: Optional[str] = None) -> List[str]:
        """
        Returns a canonical hierarchy path as strings.
        """
        path = [str(main_number)]
        if alpha_label:
            path.append(alpha_label)
        if roman_label:
            path.append(roman_label)
        return path
