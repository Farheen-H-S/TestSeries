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
        Targets markers like S->5, B->8, Z->2 only when context suggests numeric code.
        """
        if not text:
            return ""
            
        # 1. Handle isolated l, I, |, S, B, Z -> 1, 5, 8, 2
        # Use word boundaries or bracketed context
        text = re.sub(r'\b[lI|]\b', '1', text)
        
        # 2. Handle O -> 0, S -> 5, B -> 8, Z -> 2 in numeric context
        # Only if surrounded by digits or common header markers
        text = re.sub(r'(?<=\d)O|O(?=\d)', '0', text)
        text = re.sub(r'(?<=\d)S|S(?=\d)', '5', text)
        text = re.sub(r'(?<=\d)B|B(?=\d)', '8', text)
        text = re.sub(r'(?<=\d)Z|Z(?=\d)', '2', text)
        
        # Specific bracketed fixes (a common pattern for ICAI sub-questions)
        text = re.sub(r'\(S\)', '(5)', text)
        text = re.sub(r'\(B\)', '(8)', text)
        
        return text

    @staticmethod
    def normalize_header(raw_header: str) -> List[str]:
        """
        Converts a raw header into a canonical hierarchy path [main, sub, sub_sub].
        Uses tokenisation to ensure 1(a)(i) is parsed in order.
        """
        # OCR correct ONLY for identification
        header = Normalizer.ocr_correct(raw_header.strip())
        
        # Tokenisation using regex to split into components: 1, (a), (i)
        # We look for digits followed by optional bracketed labels
        path = []
        
        # 1. Main Number
        main_match = re.search(r'(\d+)', header)
        if main_number_str := (main_match.group(1) if main_match else None):
            path.append(main_number_str)
            current_pos = main_match.end()
        else:
            current_pos = 0
            
        # 2. Sequential bracketed labels: (a), (i)
        # We search from where the main number ended to keep order
        label_regex = re.compile(r'\(([^)]+)\)')
        for match in label_regex.finditer(header, current_pos):
            label = match.group(1).strip().lower()
            if label:
                path.append(label)
                
        # If no path found (e.g. just "a."), try a fallback for simple labels
        if not path:
            fallback_match = re.match(r'^([a-zA-Z1-9]|[ivxIVX]+)[.)]', header)
            if fallback_match:
                label = fallback_match.group(1).lower()
                path.append(label)

        return path
