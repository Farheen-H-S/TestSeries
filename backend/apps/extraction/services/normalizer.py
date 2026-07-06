import re
from typing import List, Tuple, Optional

class Normalizer:
    """
    Standardizes headers and handles deterministic OCR corrections.

    ARCHITECTURAL NOTE — OCR ordering constraint:
    -----------------------------------------------
    OCR correction is applied AFTER a regex pattern has already matched the
    raw document text (inside normalize_header). This means:

      - Corrections that operate on the BODY of an already-matched header
        (e.g. "1S0" → "150", digit-adjacent S) work correctly.

      - Corrections that try to fix the KEYWORD portion of a header
        (e.g. "Question S" → "Question 5") are ARCHITECTURALLY IMPOSSIBLE
        here, because the regex pattern `Question\\s+(\\d+)` requires a digit
        in the capture group and will never match "Question S" in the first
        place. Such a header never reaches normalize_header.

    Consequence: OCR lookbehind rules of the form
        `(?<=Question\\s)S`  →  '5'
    were previously present but are UNREACHABLE dead code.
    They have been removed. The correct place to handle "Question S" would
    be a pre-scan normalization pass over the raw document text. That is out
    of scope because it would require re-mapping character offsets, which would
    break the absolute-offset guarantee used by page-lookup and persistence.

    The rules that DO execute (and are correct to keep):
      - Digit-adjacent substitutions: S→5, O→0, B→8, Z→2 when surrounded by digits.
      - Isolated l/I/| → 1 at word boundaries.
    These fire on the captured raw_header text, which has already been matched.
    """

    @staticmethod
    def ocr_correct(text: str) -> str:
        """
        Applies deterministic OCR correction on an already-matched header string.

        Rules that are reachable (fire on matched header text):
          1. Isolated l, I, | → 1 at word boundaries.
          2. O → 0, S → 5, B → 8, Z → 2 when surrounded by other digits.

        Rules that are NOT included (unreachable given current regex architecture):
          - Lookbehind corrections like `(?<=Question\\s)S → 5`.
            These would only fire if "Question S" had already been matched,
            which cannot happen because the question-header regex requires \\d+.
        """
        if not text:
            return ""

        # Rule 1: Isolated OCR glyphs for digit 1 at word boundaries
        text = re.sub(r'\b[lI|]\b', '1', text)

        # Rule 2: Single-character substitutions when sandwiched between digits
        text = re.sub(r'(?<=\d)O|O(?=\d)', '0', text)
        text = re.sub(r'(?<=\d)S|S(?=\d)', '5', text)
        text = re.sub(r'(?<=\d)B|B(?=\d)', '8', text)
        text = re.sub(r'(?<=\d)Z|Z(?=\d)', '2', text)

        return text

    @staticmethod
    def normalize_header(raw_header: str) -> List[str]:
        """
        Converts a raw header string into a canonical hierarchy path list.
        Example: "Question 1(a)(i)" → ["1", "a", "i"]

        Steps:
          1. Apply OCR correction on the captured header text.
          2. Extract the leading main number (digits).
          3. Extract sequential bracketed sub-labels in order.
          4. Fallback for simple "a." / "a)" style labels.
        """
        header = Normalizer.ocr_correct(raw_header.strip())

        path = []

        # Step 1: Leading main number
        main_match = re.search(r'(\d+)', header)
        if main_match:
            path.append(main_match.group(1))
            current_pos = main_match.end()
        else:
            current_pos = 0

        # Step 2: Sequential bracketed sub-labels after the main number
        label_regex = re.compile(r'\(([^)]+)\)')
        for match in label_regex.finditer(header, current_pos):
            label = match.group(1).strip().lower()
            if label:
                path.append(label)

        # Step 3: Fallback for simple "a." / "a)" style with no main number
        if not path:
            fallback = re.match(r'^([a-zA-Z]|[ivxIVX]+)[.)]', header)
            if fallback:
                path.append(fallback.group(1).lower())

        return path
