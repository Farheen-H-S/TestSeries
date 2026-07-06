import sys
import os
import textwrap

# Add the project root to sys.path
# Assuming current dir is backend
sys.path.append(os.getcwd())

import unittest
from apps.extraction.services.question_parser import QuestionParser
from apps.extraction.services.answer_parser import AnswerParser
from apps.extraction.services.extraction_patterns import get_default_parser_config
from apps.extraction.services.types import QuestionLevel

class ParserRegressionTests(unittest.TestCase):
    def setUp(self):
        self.config = get_default_parser_config()
        self.q_parser = QuestionParser(self.config)
        self.a_parser = AnswerParser(self.config)
        self.offsets = [(0, 1), (1000, 2)]

    def test_nested_hierarchy(self):
        text = textwrap.dedent("""
            Question 1
            This is q1 text.
            (a)
            This is sub q (a)
            (i)
            This is sub-sub q (i)
            (ii)
            This is sub-sub q (ii)
            (b)
            This is sub q (b)
        """).strip()
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 5)
        self.assertEqual(parsed[0].hierarchy_path, ["1"])
        self.assertEqual(parsed[1].hierarchy_path, ["1", "a"])
        self.assertEqual(parsed[2].hierarchy_path, ["1", "a", "i"])
        self.assertEqual(parsed[3].hierarchy_path, ["1", "a", "ii"])
        self.assertEqual(parsed[4].hierarchy_path, ["1", "b"])

    def test_overlapping_match_resolution(self):
        # "Question 1(b)" matches both "Question 1" and "1(b)"
        # Should prefer the longer match "Question 1(b)"
        text = "Question 1(b)\nSome text."
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].hierarchy_path, ["1", "b"])

    def test_ocr_correction_in_headers(self):
        # Case A: Bracketed label (S) stays as sub-label 's', NOT corrected to '5'.
        # Sub-question brackets contain letters; bracket->digit corrections are for marks only.
        text = "Question 1\n(S)\nText"
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[1].hierarchy_path, ["1", "s"])

        # Case B: Verify normalizer OCR correction fires on matched header text.
        # "Question 1S0" -> ocr_correct("Question 1S0") -> "Question 150" (S between 1,0)
        # Then normalize_header extracts main digit -> ['150']
        # NOTE: The regex matches "Question \d+" and the matched raw_header is "Question 1S0".
        # The normalizer then OCR-corrects within that raw text.
        from apps.extraction.services.normalizer import Normalizer
        result = Normalizer.normalize_header("Question 1S0")
        self.assertEqual(result, ["150"])

    def test_roman_numeral_detection(self):
        text = "Question 1\n(a)\n(i)\n(v)\n(x)"
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(parsed[2].hierarchy_path, ["1", "a", "i"])
        self.assertEqual(parsed[3].hierarchy_path, ["1", "a", "v"])
        self.assertEqual(parsed[4].hierarchy_path, ["1", "a", "x"])

    def test_paragraph_false_positive_rejection(self):
        text = textwrap.dedent("""
            Question 1
            This is a paragraph. 1. This should not be a new question because it is in a sentence.
            2. This is a new question because it is at the start of a line.
        """).strip()
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].hierarchy_path, ["1"])
        self.assertEqual(parsed[1].hierarchy_path, ["2"])

    def test_illegal_hierarchy_rejection(self):
        # Roman (i) MUST follow Alpha (a) in our strict rules
        # 1 -> (i) should be REJECTED with a clear reason
        text = "Question 1\n(i)\nText"
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 1) # (i) was rejected
        
        # Verify diagnostic reason
        rejection = self.q_parser.diagnostics.rejected_headers[0]
        self.assertEqual(rejection["reason"], "illegal hierarchy transition: roman must follow alpha")

    def test_starting_sequence_validation(self):
        # Starting with (i) should be rejected
        text = "(i)\nText"
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 0)
        self.assertEqual(self.q_parser.diagnostics.rejected_headers[0]["reason"], "invalid starting numbering sequence")

    def test_complex_header_normalization(self):
        # Testing OCR and order
        text = "Question 1(b)(ii)\nText"
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(parsed[0].hierarchy_path, ["1", "b", "ii"])

if __name__ == "__main__":
    unittest.main()
