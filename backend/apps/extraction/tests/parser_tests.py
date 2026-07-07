import sys
import os
import textwrap

# Add the project root to sys.path
sys.path.append(os.getcwd())

import unittest
from apps.extraction.services.question_parser import QuestionParser
from apps.extraction.services.answer_parser import AnswerParser
from apps.extraction.services.extraction_patterns import get_default_parser_config
from apps.extraction.services.types import QuestionLevel
from apps.extraction.services.marks_extractor import MarksExtractor

class ParserRegressionTests(unittest.TestCase):
    def setUp(self):
        self.config = get_default_parser_config()
        self.q_parser = QuestionParser(self.config)
        self.a_parser = AnswerParser(self.config)
        # 3 pages offsets: page 1 starts at 0, page 2 starts at 1000, page 3 starts at 2000
        self.offsets = [(0, 1), (1000, 2), (2000, 3)]

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
        self.assertEqual(parsed[0].raw_header, "Question 1(b)")

        # "Question 2(a)(ii)" should prefer the full match
        text2 = "Question 2(a)(ii)\nSome nested text."
        parsed2 = self.q_parser.parse(text2, self.offsets)
        self.assertEqual(len(parsed2), 1)
        self.assertEqual(parsed2[0].hierarchy_path, ["2", "a", "ii"])
        self.assertEqual(parsed2[0].raw_header, "Question 2(a)(ii)")

    def test_ocr_pre_normalization(self):
        # Realistic OCR cases seen in scanned ICAI papers
        # l -> 1, I -> 1, O -> 0, S -> 5, B -> 8, Z -> 2
        ocr_cases = [
            ("Question l\nText for q1", ["1"], "Question l"),
            ("Question I\nText for q1", ["1"], "Question I"),
            ("Question O\nText for q0", ["0"], "Question O"),
            ("Question S\nText for q5", ["5"], "Question S"),
            ("Question B\nText for q8", ["8"], "Question B"),
            ("Question Z\nText for q2", ["2"], "Question Z"),
            # Nested OCR headers
            ("Question l(a)\nText for q1(a)", ["1", "a"], "Question l(a)"),
            ("Question I(a)\nText for q1(a)", ["1", "a"], "Question I(a)"),
            ("Question B(a)\nText for q8(a)", ["8", "a"], "Question B(a)"),
            ("Question S(a)\nText for q5(a)", ["5", "a"], "Question S(a)"),
            # Digit-sandwiched OCR corrections
            ("Question 12S\nText for q125", ["125"], "Question 12S"),
            ("Question 1O5\nText for q105", ["105"], "Question 1O5"),
        ]
        for input_text, expected_path, expected_raw in ocr_cases:
            with self.subTest(input_text=input_text):
                parsed = self.q_parser.parse(input_text, self.offsets)
                self.assertEqual(len(parsed), 1)
                self.assertEqual(parsed[0].hierarchy_path, expected_path)
                self.assertEqual(parsed[0].raw_header, expected_raw)

    def test_ocr_no_corruption_of_subquestions(self):
        # Alphabetical subquestions like b., b), s), z. should NOT be corrupted by OCR
        text = textwrap.dedent("""
            Question 1
            (a)
            Text
            b.
            Text
            s)
            Text
            z.
            Text
        """).strip()
        parsed = self.q_parser.parse(text, self.offsets)
        # Since hierarchy transition allows a -> b, the "b." should be parsed as subquestion "b" of "1"
        self.assertEqual(len(parsed), 5)
        self.assertEqual(parsed[0].hierarchy_path, ["1"])
        self.assertEqual(parsed[1].hierarchy_path, ["1", "a"])
        self.assertEqual(parsed[2].hierarchy_path, ["1", "b"]) # "b." is preserved!
        # "s)" and "z." are also preserved as sub-labels (they don't become main questions "5" and "2")
        self.assertEqual(parsed[3].hierarchy_path, ["1", "s"])
        self.assertEqual(parsed[4].hierarchy_path, ["1", "z"])

    def test_ocr_no_corruption_of_roman_numerals(self):
        # Roman numeral list items like "I." at the start of a line must not become "1."
        text = textwrap.dedent("""
            Question 1
            (a)
            I.
            Some text.
        """).strip()
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 2) # "I." is ignored (not corrupted to "1.", which would start a new hierarchy)

    def test_ocr_correction_in_headers(self):
        # Case A: Bracketed label (S) stays as sub-label 's', NOT corrected to '5'.
        # Sub-question brackets contain letters; bracket->digit corrections are for marks only.
        text = "Question 1\n(S)\nText"
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[1].hierarchy_path, ["1", "s"])

        # Case B: Verify normalizer OCR correction fires on matched header text.
        # "Question 1S0" -> ocr_correct("Question 1S0") -> "Question 150" (S between 1,0)
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

    def test_stateless_diagnostics(self):
        # Call parse_with_diagnostics
        text = "Question 1\n(i)\nText"
        result = self.q_parser.parse_with_diagnostics(text, self.offsets)
        self.assertEqual(len(result.questions), 1)
        self.assertEqual(len(result.diagnostics.rejected_headers), 1)
        self.assertEqual(result.diagnostics.rejected_headers[0]["reason"], "illegal hierarchy transition: roman must follow alpha")

        # Verify that instance diagnostics also works (backward compatibility)
        self.assertEqual(len(self.q_parser.diagnostics.rejected_headers), 0) # parse_with_diagnostics does not mutate instance state
        
        # Calling parse mutates instance state
        self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(self.q_parser.diagnostics.rejected_headers), 1)

    def test_marks_extraction_formats(self):
        extractor = MarksExtractor(self.config)
        formats = [
            ("(5 Marks)", 5),
            ("[5 Marks]", 5),
            ("Marks: 5", 5),
            ("Marks - 5", 5),
            ("5 Marks", 5),
            ("Explain the method. (5)", 5),
            ("Explain the process. [5]", 5),
            ("Explain the system. 5M", 5),
            ("Explain the theory. 5 M", 5),
            # Marks on their own line
            ("Explain valuation.\n(5)", 5),
            ("Explain valuation.\n[5]", 5),
            # Marks followed by transition text
            ("Explain valuation. (5) OR", 5),
            ("Explain valuation. (5) Compulsory", 5),
        ]
        for text, expected in formats:
            with self.subTest(text=text):
                val = extractor.extract(text)
                self.assertEqual(val, expected)

        # Verify exclusions & structural position validation for weak patterns
        false_positives = [
            ("Company issued 5m shares.", None),
            ("5 M Ltd. issued shares.", None),
            ("Pipeline length is 5 m.", None),
            ("Section 5 of the Act", None),
            ("Refer to Page 5 of guidelines", None),
            ("Question 5 is compulsory", None),
            ("Under Ind AS 10 guidance", None),
            ("This occurred in year 2024.", None),
            ("5 M employees were surveyed.", None),
            ("We bought 5m packets of seeds.", None),
            ("(1) Point one explanation", None), # List items should be rejected!
        ]
        for text, expected in false_positives:
            with self.subTest(text=text):
                val = extractor.extract(text)
                self.assertEqual(val, expected)

    def test_page_lookup(self):
        from apps.extraction.services.hierarchy_utils import HierarchyUtils
        page_keys = [x[0] for x in self.offsets]
        
        # Offset 50 is in page 1 (0 to 999)
        self.assertEqual(HierarchyUtils.get_page_num_fast(50, self.offsets, page_keys), 1)
        # Offset 1050 is in page 2 (1000 to 1999)
        self.assertEqual(HierarchyUtils.get_page_num_fast(1050, self.offsets, page_keys), 2)
        # Offset 2500 is in page 3 (2000+)
        self.assertEqual(HierarchyUtils.get_page_num_fast(2500, self.offsets, page_keys), 3)

if __name__ == "__main__":
    unittest.main()
