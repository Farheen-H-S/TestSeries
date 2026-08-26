import re
from typing import List, Optional, Tuple

class HierarchyUtils:
    """
    Shared utilities for hierarchy decomposition and stack management.
    Ensures deterministic transitions across both Question and Answer parsers.
    """
    
    # Standard ICAI Roman Numerals (i to xv)
    ROMAN_REGEX = re.compile(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv)$', re.IGNORECASE)

    @staticmethod
    def decompose_path(path: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Decomposes a normalized hierarchy path into components.
        Priority: 1. Main Number (Digits), 2. Roman Numerals, 3. Alpha Labels.
        """
        main = None
        alpha = None
        roman = None
        
        for p in path:
            if p.isdigit() and main is None:
                main = p
            elif HierarchyUtils.ROMAN_REGEX.match(p):
                roman = p
            elif len(p) == 1 and p.isalpha():
                alpha = p
                
        return main, alpha, roman

    @staticmethod
    def update_hierarchy_stack(stack: List[str], new_path: List[str]):
        """
        Updates a stateful hierarchy stack based on a new path match.
        Deterministic logic to handle depth transitions.
        """
        if not new_path:
            return

        # Case study decimal paths (e.g. ['1', '1'], ['1', '2'])
        if len(new_path) == 2 and new_path[0].isdigit() and new_path[1].isdigit():
            stack.clear()
            stack.extend(new_path)
            return

        main, alpha, roman = HierarchyUtils.decompose_path(new_path)

        if main:
            # Transitioning to a new MAIN level (e.g. 1 -> 2)
            stack.clear()
            stack.append(main)
            if alpha: stack.append(alpha)
            if roman: stack.append(roman)
        elif alpha:
            # Transitioning to/within a SUB level (e.g. 1 -> (a) or (a) -> (b))
            # Must have a main level to attach to, OR be a mainless alpha-only document
            if not stack:
                stack.append(alpha)
                if roman: stack.append(roman)
                return

            # Decimal Case Study parent (e.g. ['2', '3'] -> ['2', '3', 'a'], or ['2', '3', 'a'] -> ['2', '3', 'b'])
            if len(stack) >= 2 and stack[0].isdigit() and stack[1].isdigit():
                while len(stack) > 2:
                    stack.pop()
                stack.append(alpha)
                if roman: stack.append(roman)
                return

            while len(stack) > 1:
                stack.pop()
            if stack[0].isdigit():
                stack.append(alpha)
            else:
                stack[0] = alpha
            if roman: stack.append(roman)
        elif roman:
            # Transitioning to/within a SUB_SUB level (e.g. (a) -> (i), (i) -> (ii), or 16 -> (i))
            if len(stack) < 1:
                return

            # Decimal Case Study parent (e.g. ['2', '3'] or ['2', '3', 'a'])
            if len(stack) >= 2 and stack[0].isdigit() and stack[1].isdigit():
                if len(stack) == 2:
                    stack.append(roman)
                    return
                elif len(stack) == 3 and HierarchyUtils.ROMAN_REGEX.match(stack[2]):
                    stack[2] = roman
                    return
                elif len(stack) == 3:  # e.g. ['2', '3', 'a'] -> ['2', '3', 'a', 'i']
                    stack.append(roman)
                    return
                elif len(stack) == 4 and HierarchyUtils.ROMAN_REGEX.match(stack[3]):
                    stack[3] = roman
                    return

            # If stack is mainless starting with alpha (e.g. ['a']), we can append roman
            if not stack[0].isdigit() and len(stack) == 1:
                stack.append(roman)
                return

            # If stack is ['1'], we append roman directly (relaxed main -> roman rule)
            if stack[0].isdigit() and len(stack) == 1:
                stack.append(roman)
                return

            # If stack is ['1', 'i'] (no alpha, just main and active roman), replace roman
            if stack[0].isdigit() and len(stack) == 2 and HierarchyUtils.ROMAN_REGEX.match(stack[1]):
                stack[1] = roman
                return

            # Otherwise, normal alpha -> roman transition
            if len(stack) < 2:
                return
            while len(stack) > 2:
                stack.pop()
            stack.append(roman)


    @staticmethod
    def get_page_num_fast(offset: int, page_offsets: List[Tuple[int, int]], page_keys: List[int]) -> int:
        """
        Finds the page number for a given character offset using binary search on precomputed keys.
        """
        if not page_keys: return 1
        import bisect
        idx = bisect.bisect_right(page_keys, offset) - 1
        return page_offsets[max(0, idx)][1]


def build_hierarchy_key(path: List[str]) -> str:
    normalized = []
    for part in path:
        if part is None:
            continue
        part = str(part).strip()
        if not part:
            continue
        normalized.append(part)
    return ".".join(normalized)


