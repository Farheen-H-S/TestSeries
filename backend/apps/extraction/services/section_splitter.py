from typing import Tuple

class SectionSplitter:
    """
    Simple index-based text splitter.
    """
    
    def split(self, text: str, boundary_index: int) -> Tuple[str, str]:
        """
        Splits text into two parts at the given character index.
        """
        if boundary_index is None or boundary_index < 0 or boundary_index >= len(text):
            return text, ""
            
        return text[:boundary_index], text[boundary_index:]
