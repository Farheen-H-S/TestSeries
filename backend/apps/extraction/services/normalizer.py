import re
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

class Normalizer:
    # Configurable initial defaults for OCR anomaly detection, expected to be tuned after testing
    OCR_ANOMALY_CHAR_PERCENTAGE_THRESHOLD = 0.015
    OCR_ANOMALY_PER_PAGE_THRESHOLD = 50.0

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

        # Rule 1: Isolated OCR glyphs for digit 1 at word boundaries (excluding bracketed Roman numerals)
        text = re.sub(r'(?<!\()\b[lI|]\b(?!\))', '1', text)

        # Rule 2: Single-character substitutions when sandwiched between digits
        text = re.sub(r'(?<=\d)O|O(?=\d)', '0', text)
        text = re.sub(r'(?<=\d)S|S(?=\d)', '5', text)
        text = re.sub(r'(?<=\d)B|B(?=\d)', '8', text)
        text = re.sub(r'(?<=\d)Z|Z(?=\d)', '2', text)

        return text

    @staticmethod
    def pre_normalize_ocr(text: str) -> str:
        """
        Performs 1-to-1 character replacements on the input text to fix common OCR errors
        before regex matching runs. This preserves offsets exactly.
        
        INVARIANT:
        The length of the returned normalized text must exactly match the length of the
        input text (i.e. len(normalized) == len(original)) to guarantee absolute offset safety.
        """
        if not text:
            return ""

        original_text = text

        # Normalize line endings to \n while preserving length:
        # \r\n -> " \n"
        # \r   -> "\n"
        text = text.replace('\r\n', ' \n').replace('\r', '\n')

        ocr_map = {
            'l': '1', 'I': '1', '|': '1',
            'O': '0', 'o': '0',
            'S': '5', 's': '5',
            'B': '8', 'b': '8',
            'Z': '2', 'z': '2'
        }
        
        def repl_prefix(match: re.Match) -> str:
            prefix = match.group(1)
            mistake_str = match.group(2)
            corrected = "".join(ocr_map.get(ch, ch) for ch in mistake_str)
            return prefix + corrected

        # Matches specific header prefixes followed by label strings (digits or OCR glyphs):
        # e.g. Question S, Question 12S, Question 1O5, Q. B, Ans O, Solution I
        # Prefix pattern matches case-insensitively and replaces characters without changing text length.
        text = re.sub(
            r'(?i)\b(Question\s+(?:No\.\s*)?|Q\.?\s?|Answer\s+(?:to\s+)?(?:Question\s+)?(?:No\.\s*)?|Ans\.?\s*|Solution\s*)([0-9lI|OSBZosbz]+)(?=\s|\(|\.|\)|$)',
            repl_prefix,
            text
        )

        if logger.isEnabledFor(logging.DEBUG):
            changes = sum(1 for c1, c2 in zip(original_text, text) if c1 != c2)
            if changes > 0:
                logger.debug("OCR pre-normalization applied | text_length=%d | changed_chars=%d", len(text), changes)

        return text

    @staticmethod
    def normalize_header(raw_header: str) -> List[str]:
        """
        Converts a raw header string into a canonical hierarchy path list.
        Example: "Question 1(a)(i)" → ["1", "a", "i"]

        Steps:
          1. Apply pre-normalize OCR correction on the captured header text.
          2. Apply basic OCR correction.
          3. Extract the leading main number (digits).
          4. Extract sequential bracketed sub-labels in order.
          5. Fallback for simple "a." / "a)" style labels.
        """
        header = Normalizer.pre_normalize_ocr(raw_header.strip())
        header = Normalizer.ocr_correct(header)

        path = []

        # Step 1: Check for decimal case-study style header (e.g. "1.1", "1.2", "2.1")
        decimal_match = re.match(r'^([1-9])\.([1-9]|1[0-5])\b', header)
        if decimal_match:
            path.extend([decimal_match.group(1), decimal_match.group(2)])
            current_pos = decimal_match.end()
        else:
            # Leading main number
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
