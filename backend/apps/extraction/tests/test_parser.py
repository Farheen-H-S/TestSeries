import sys
import os
import textwrap

# Add the project root to sys.path
sys.path.append(os.getcwd())

import unittest
from apps.extraction.services.question_parser import QuestionParser
from apps.extraction.services.answer_parser import AnswerParser
from apps.extraction.services.extraction_patterns import get_default_parser_config
from apps.extraction.services.types import QuestionLevel, AnswerSource
from apps.extraction.services.marks_extractor import MarksExtractor
from apps.extraction.services.answer_matcher import AnswerMatcher
from apps.extraction.services.normalizer import Normalizer
from apps.extraction.services.question_classifier import QuestionClassifier

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

    def test_relaxed_roman_hierarchy_transition(self):
        # Roman (i) is permitted to directly follow Main (1) when no Alpha is active
        text = "Question 1\n(i)\nText"
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].hierarchy_path, ["1"])
        self.assertEqual(parsed[1].hierarchy_path, ["1", "i"])

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
        # Call parse_with_diagnostics starting with Roman to check diagnostics rejections
        text = "(i)\nText"
        result = self.q_parser.parse_with_diagnostics(text, self.offsets)
        self.assertEqual(len(result.questions), 0)
        self.assertEqual(len(result.diagnostics.rejected_headers), 1)
        self.assertEqual(result.diagnostics.rejected_headers[0]["reason"], "invalid starting numbering sequence")

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
            ("Explain valuation.\n5M", 5),
            # Transition text
            ("Explain valuation. (5) OR", 5),
            ("Explain valuation. (5) Compulsory", 5),
            ("Explain valuation. (5) Attempt Any One", 5),
            # Punctuation variations
            ("Explain. ( 5 )", 5),
            ("Explain. [  5  ]", 5),
            ("Explain. Marks:5", 5),
            ("Explain. Marks - 5", 5),
            # OCR noise variations
            ("Explain the term. 5M.", 5),
            ("Explain the term. 5 M.", 5),
            ("Explain the term. 5M:", 5),
            ("Explain the term. 5 M:", 5),
            # Context-bound exclusions (fixed contexts like Ind AS 10)
            ("Explain Ind AS 10. (5 Marks)", 5),
            ("Explain section 135. (5 Marks)", 5),
        ]
        for text, expected in formats:
            with self.subTest(text=text):
                val = extractor.extract(text)
                self.assertEqual(val, expected)

        # Verify exclusions & structural position validation for weak patterns
        false_positives = [
            # Measurements (should be ignored)
            ("Company issued 5m shares.", None),
            ("Pipeline length is 5 m.", None),
            ("We bought 5m packets of seeds.", None),
            ("The container capacity is 5 M employees.", None),
            ("5 M employees were surveyed.", None),
            ("5 m pipe", None),
            ("Pipeline length: 5 m.", None),
            ("Diameter is (5) inches.", None),
            ("The diameter is (5) inches.", None),
            # Company names
            ("5 M Ltd. issued shares.", None),
            ("ABC Ltd. has 5 M capital.", None),
            # General OCR / Number noise
            ("We found some 5 m. of pipe.", None),
            ("Refer to page 5.", None),
            ("Section 5 of the act.", None),
            ("Under Ind AS 10 guidance", None),
            ("This occurred in year 2024.", None),
            # List items starting lines
            ("(1) Point one explanation", None),
            ("[2] Point two explanation", None),
            ("1. Point one", None),
            ("a) Point a", None),
        ]
        for text, expected in false_positives:
            with self.subTest(text=text):
                val = extractor.extract(text)
                self.assertEqual(val, expected)

    def test_marks_same_priority_selection(self):
        extractor = MarksExtractor(self.config)
        # Priorities of both (5) and (4) are equal. Should choose the one occurring later in the question: (4)
        text = "Explain the (5) methods. (4)"
        val = extractor.extract(text)
        self.assertEqual(val, 4)

    def test_unknown_layout_self_matching(self):
        # UNKNOWN layout question-only paper
        # Ensure that Question 1 does NOT become its own Answer 1 because their match offsets overlap
        q_parser = QuestionParser(self.config)
        a_parser = AnswerParser(self.config)
        matcher = AnswerMatcher()
        
        text = "1. Define goodwill and explain its types."
        questions = q_parser.parse(text, self.offsets)
        answers = a_parser.parse(text, self.offsets)
        
        self.assertEqual(len(questions), 1)
        self.assertEqual(len(answers), 1)
        
        # Verify matching logic rejects this because of overlapping header offsets
        result = matcher.match(questions, answers)
        self.assertEqual(len(result.matches), 0)
        self.assertIn("1", result.diagnostics.unmatched_questions)
        self.assertIn("1", result.diagnostics.unmatched_answers)

    def test_cr_lf_documents(self):
        # CR-only line endings
        text_cr = "Question 1\r(a)\rDescribe goodwill.\r(b)\rExplain valuation."
        parsed_cr = self.q_parser.parse(text_cr, self.offsets)
        self.assertEqual(len(parsed_cr), 3)
        self.assertEqual(parsed_cr[0].hierarchy_path, ["1"])
        self.assertEqual(parsed_cr[1].hierarchy_path, ["1", "a"])
        self.assertEqual(parsed_cr[2].hierarchy_path, ["1", "b"])

        # CRLF line endings
        text_crlf = "Question 1\r\n(a)\r\nDescribe goodwill.\r\n(b)\r\nExplain valuation."
        parsed_crlf = self.q_parser.parse(text_crlf, self.offsets)
        self.assertEqual(len(parsed_crlf), 3)
        self.assertEqual(parsed_crlf[0].hierarchy_path, ["1"])
        self.assertEqual(parsed_crlf[1].hierarchy_path, ["1", "a"])
        self.assertEqual(parsed_crlf[2].hierarchy_path, ["1", "b"])

    def test_ocr_normalization_preserves_length(self):
        # The invariant len(normalized) == len(original) must be strictly enforced.
        test_strings = [
            "Question S0",
            "Question I(a)",
            "Question l(b)",
            "Question 1S0",
            "Question 12S",
            "Question 1O5",
            "Q. B",
            "Ans O",
            "Solution I",
            "  l.  ",
            "  |.  "
        ]
        for s in test_strings:
            normalized = Normalizer.pre_normalize_ocr(s)
            self.assertEqual(len(normalized), len(s), f"Length mismatch for: {s}")

    def test_question_classifier_punctuation_boundary(self):
        # Classifier matches with trailing punctuation in keywords (e.g. MR., MRS.)
        classifier = QuestionClassifier({
            "CASE_STUDY": ["MR. SMITH", "MRS. JONES", "DR. WATSON"],
            "THEORY": ["DEFINE", "EXPLAIN"]
        })
        self.assertEqual(classifier.classify("Explain the duties of Mr. Smith."), "CASE_STUDY")
        self.assertEqual(classifier.classify("Explain the process to Mrs. Jones."), "CASE_STUDY")
        self.assertEqual(classifier.classify("We consulted Dr. Watson."), "CASE_STUDY")
        self.assertEqual(classifier.classify("Define valuation."), "THEORY")

    def test_section_wise_pagination_offset(self):
        # Verify that questions and answers parsed in a section-wise layout
        # (with base_offset) are assigned the correct absolute page numbers.
        from apps.extraction.services.question_parser import QuestionParser
        from apps.extraction.services.answer_parser import AnswerParser
        
        # 3 pages offsets: page 1 starts at 0, page 2 starts at 1000, page 3 starts at 2000
        offsets = [(0, 1), (1000, 2), (2000, 3)]
        
        # Answer parsed at relative offset 100 with base_offset 1000 should map to page 2 (1100 absolute)
        a_parser = AnswerParser(self.config)
        parsed = a_parser.parse("Solution 1\nSome answer text", offsets, base_offset=1000)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].start_page, 2)
        
        q_parser = QuestionParser(self.config)
        parsed_q = q_parser.parse("Question 1\nSome question text", offsets, base_offset=1000)
        self.assertEqual(len(parsed_q), 1)
        self.assertEqual(parsed_q[0].start_page, 2)

    def test_page_lookup(self):
        from apps.extraction.services.hierarchy_utils import HierarchyUtils
        page_keys = [x[0] for x in self.offsets]
        
        # Offset 50 is in page 1 (0 to 999)
        self.assertEqual(HierarchyUtils.get_page_num_fast(50, self.offsets, page_keys), 1)
        # Offset 1050 is in page 2 (1000 to 1999)
        self.assertEqual(HierarchyUtils.get_page_num_fast(1050, self.offsets, page_keys), 2)
        # Offset 2500 is in page 3 (2000+)
        self.assertEqual(HierarchyUtils.get_page_num_fast(2500, self.offsets, page_keys), 3)

    def test_mainless_alpha_hierarchy_transition(self):
        text = "(a)\nFirst subquestion\n(b)\nSecond subquestion\n(i)\nFirst sub-subquestion"
        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0].hierarchy_path, ["a"])
        self.assertEqual(parsed[1].hierarchy_path, ["b"])
        self.assertEqual(parsed[2].hierarchy_path, ["b", "i"])

    def test_marks_nested_exclusion(self):
        extractor = MarksExtractor(self.config)
        self.assertEqual(extractor.extract("Explain Section 135(5)."), None)
        self.assertEqual(extractor.extract("Explain Section 135(5). (5 Marks)"), 5)
        self.assertEqual(extractor.extract("Explain Ind AS 10(1)."), None)
        self.assertEqual(extractor.extract("Explain Ind AS 10(1). [5 Marks]"), 5)

    def test_build_hierarchy_key(self):
        from apps.extraction.services.hierarchy_utils import build_hierarchy_key
        
        # Test edge cases
        self.assertEqual(build_hierarchy_key([]), "")
        self.assertEqual(build_hierarchy_key(["1"]), "1")
        self.assertEqual(build_hierarchy_key(["1", "a"]), "1.a")
        self.assertEqual(build_hierarchy_key(["1", "a", "i"]), "1.a.i")
        self.assertEqual(build_hierarchy_key(["1", "a", "i", "A", "I"]), "1.a.i.A.I")
        
        # Test whitespace trimming and none/empty string filtering
        self.assertEqual(build_hierarchy_key([" 1 ", " a "]), "1.a")
        self.assertEqual(build_hierarchy_key(["1", None, "a"]), "1.a")
        self.assertEqual(build_hierarchy_key(["1", "", "a"]), "1.a")
        
        # Test equivalent path serialization (whitespace-insensitive uniqueness)
        key1 = build_hierarchy_key(["1", "a"])
        key2 = build_hierarchy_key(["1 ", " a"])
        self.assertEqual(key1, "1.a")
        self.assertEqual(key2, "1.a")
        self.assertEqual(key1, key2)

    def test_shared_question_context_grouping(self):
        text = textwrap.dedent("""
            Revision Test Paper
            Time Allowed: 3 Hours

            Case Scenario A
            An entity enters into a contract with customer A...
            Based on the facts given above, answer Questions 1 to 2 below:

            1. What is the standalone selling price?
            2. How much revenue will be recognised?

            Case Scenario B
            The following Consolidated Balance Sheet relates to M Ltd...

            3. Calculate goodwill of M Ltd.
            4. Compute non-controlling interest.
        """).strip()

        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 4)

        # Context A for Q1 & Q2
        self.assertIn("Case Scenario A", parsed[0].shared_context)
        self.assertIn("customer A", parsed[0].shared_context)
        self.assertNotIn("Revision Test Paper", parsed[0].shared_context)
        self.assertEqual(parsed[0].shared_context, parsed[1].shared_context)


        # Context B for Q3 & Q4
        self.assertIn("Case Scenario B", parsed[2].shared_context)
        self.assertIn("Consolidated Balance Sheet", parsed[2].shared_context)
        self.assertEqual(parsed[2].shared_context, parsed[3].shared_context)

        # Verify Context A is terminated when Context B begins
        self.assertNotEqual(parsed[0].shared_context, parsed[2].shared_context)

    def test_hierarchical_answer_working_notes(self):
        answer_text = textwrap.dedent("""
            Answer to Multiple Choice Questions
            1. Option (c) ₹ 12
            2. Option (a) ₹ 188.68

            Question 6
            Consolidated Balance Sheet of M Ltd and its subsidiary N Ltd.

            Working Notes:
            1. Shareholding pattern
            M Ltd holds 80% shares.
            2. Analysis of Retained Earnings
            Closing balance is ₹ 2,05,000.
        """).strip()

        parsed_a = self.a_parser.parse(answer_text, self.offsets)
        matcher = AnswerMatcher()

        # Questions Q1 and Q6
        q1 = self.q_parser.parse("Question 1\nWhat is standalone price?", self.offsets)
        q6 = self.q_parser.parse("Question 6\nPrepare Consolidated Balance Sheet.", self.offsets)

        # Match Q1 & Q6
        result1 = matcher.match(q1, parsed_a)
        result6 = matcher.match(q6, parsed_a)

        # Q1 should match Option (c), NOT Working Note 1
        self.assertEqual(len(result1.matches), 1)
        self.assertEqual(result1.matches[0][1].text, "Option (c) ₹ 12")

        # Q6 should match Question 6 answer and contain WorkingNote objects
        self.assertEqual(len(result6.matches), 1)
        q6_ans = result6.matches[0][1]
        self.assertEqual(len(q6_ans.working_notes), 2)
        self.assertEqual(q6_ans.working_notes[0].number, "1")
        self.assertEqual(q6_ans.working_notes[0].title, "Shareholding pattern")
        self.assertIn("80% shares", q6_ans.working_notes[0].content)

    def test_mcq_structured_table_answers(self):
        answer_text = textwrap.dedent("""
            Answer to Multiple Choice Questions
            
            [STRUCTURED_START]
            |Col1|1.|Col3|Col4|Option (c) ₹ 12|Col6|
            |---|---|---|---|---|---|
            ||**2.**|||**Option (a)** ₹ 188.68||
            ||**3.**|||**Option (d)** ₹ 11.32||
            |**4.**|**4.**|**4.**|<br> <br>|**Option (b)** The said liability will be subsequently credited to|<br>|
            |**4.**|**4.**|**4.**|<br> <br>|revenue only when the customer purchases in future using the|revenue only when the customer purchases in future using the|
            |**4.**|**4.**|**4.**|<br> <br>|discount coupon or when the coupon expires.|discount coupon or when the coupon expires.|
            ||**5.**|||**Option (c)** Contract Liability under Ind AS 115||
            [STRUCTURED_END]
            
            Question 6
            Consolidated Balance Sheet details.
        """).strip()

        parsed_a = self.a_parser.parse(answer_text, self.offsets)
        
        # Verify we parsed Questions 1 to 5 and Question 6
        # Expected count: 5 MCQ answers + 1 Descriptive Answer (6) = 6
        self.assertEqual(len(parsed_a), 6)
        
        # Verify MCQ Answers mapping and texts
        self.assertEqual(parsed_a[0].hierarchy_path, ["1"])
        self.assertEqual(parsed_a[0].text, "Option (c) ₹ 12")
        self.assertEqual(parsed_a[0].section_type.name, "MCQ_ANSWER")
        
        self.assertEqual(parsed_a[1].hierarchy_path, ["2"])
        self.assertEqual(parsed_a[1].text, "Option (a) ₹ 188.68")
        self.assertEqual(parsed_a[1].section_type.name, "MCQ_ANSWER")
        
        self.assertEqual(parsed_a[2].hierarchy_path, ["3"])
        self.assertEqual(parsed_a[2].text, "Option (d) ₹ 11.32")
        self.assertEqual(parsed_a[2].section_type.name, "MCQ_ANSWER")
        
        self.assertEqual(parsed_a[3].hierarchy_path, ["4"])
        self.assertEqual(parsed_a[3].text, "Option (b) The said liability will be subsequently credited to revenue only when the customer purchases in future using the discount coupon or when the coupon expires.")
        self.assertEqual(parsed_a[3].section_type.name, "MCQ_ANSWER")
        
        self.assertEqual(parsed_a[4].hierarchy_path, ["5"])
        self.assertEqual(parsed_a[4].text, "Option (c) Contract Liability under Ind AS 115")
        self.assertEqual(parsed_a[4].section_type.name, "MCQ_ANSWER")
        
        self.assertEqual(parsed_a[5].hierarchy_path, ["6"])
        self.assertEqual(parsed_a[5].text, "Consolidated Balance Sheet details.")
        self.assertEqual(parsed_a[5].section_type.name, "MCQ_ANSWER")

    def test_mcq_duplicate_hierarchy_resolution(self):
        # Text where regex parser matches "4." (descriptive answer block)
        # and MCQ parser also matches "4." inside the structured table.
        answer_text = textwrap.dedent("""
            Answer to Multiple Choice Questions
            
            [STRUCTURED_START]
            |Col1|4.|Col3|Col4|Option (b) Table Answer|Col6|
            [STRUCTURED_END]
            
            4. Regex Answer
            Descriptive details for Q4.
        """).strip()

        parsed_a = self.a_parser.parse(answer_text, self.offsets)
        
        # The duplicate hierarchy path ["4"] should be deduplicated to exactly one ParsedAnswer.
        # The table answer ("Option (b) Table Answer") must take precedence over the regex answer.
        self.assertEqual(len(parsed_a), 1)
        self.assertEqual(parsed_a[0].hierarchy_path, ["4"])
        self.assertEqual(parsed_a[0].text, "Option (b) Table Answer")
        self.assertEqual(parsed_a[0].source, AnswerSource.MCQ_TABLE)

    def test_working_note_reference_preservation(self):
        text = textwrap.dedent("""
            Solution 6
            Refer Working Note 1 for shareholding pattern calculations.

            Working Notes:
            1. Shareholding pattern
            Calculation details here.
        """).strip()

        parsed = self.a_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 1)
        self.assertIn("Refer Working Note 1", parsed[0].text)
        self.assertEqual(len(parsed[0].working_notes), 1)
        self.assertEqual(parsed[0].working_notes[0].number, "1")
        self.assertEqual(parsed[0].working_notes[0].title, "Shareholding pattern")
        self.assertEqual(parsed[0].working_notes[0].content, "Calculation details here.")

    def test_multi_group_context_isolation(self):
        text = textwrap.dedent("""
            Case Scenario A
            Details for scenario A...
            Based on the facts given above, answer Questions 1 to 4 below:

            1. Question 1 text?
            2. Question 2 text?
            3. Question 3 text?
            4. Question 4 text?

            Case Scenario B
            The following Balance Sheet relates to company B...
            Based on the facts given above, answer Questions 5 to 7 below:

            5. Question 5 text?
            6. Question 6 text?
            7. Question 7 text?

            Part II - Descriptive Questions

            8. Question 8 standalone text without scenario.
            9. Question 9 standalone text without scenario.
        """).strip()

        parsed = self.q_parser.parse(text, self.offsets)
        self.assertEqual(len(parsed), 9)

        # Q1 to Q4 should have Context A
        for i in range(4):
            self.assertIn("Case Scenario A", parsed[i].shared_context)

        # Q5 to Q7 should have Context B
        for i in range(4, 7):
            self.assertIn("Case Scenario B", parsed[i].shared_context)

        # Q8 and Q9 are standalone and should NOT have shared_context
        self.assertIsNone(parsed[7].shared_context)
        self.assertIsNone(parsed[8].shared_context)

    def test_word_boundary_strong_header(self):
        from apps.extraction.services.header_validator import HeaderValidator
        validator = HeaderValidator()
        
        # Genuine strong headers
        self.assertTrue(validator.is_strong_header("Question 1"))
        self.assertTrue(validator.is_strong_header("Answer 5"))
        self.assertTrue(validator.is_strong_header("Solution 3"))
        
        # Words containing substrings should NOT be strong headers
        self.assertFalse(validator.is_strong_header("Questionnaire"))
        self.assertFalse(validator.is_strong_header("Answered"))
        self.assertFalse(validator.is_strong_header("Consolidated"))

    def test_working_notes_auto_recovery_on_ocr_corruption(self):
        # Configure a short max_working_notes_length to test self-healing auto-recovery
        self.config.max_working_notes_length = 100
        
        text = textwrap.dedent("""
            Question 10
            Main answer text for question 10.

            Working Notes:
            1. Note item 1
            Calculation details.

            corrupted_header_ll_fails_validation
            Filling 150 characters of padding text to trigger max distance threshold recovery in working notes zone...
            Padding padding padding padding padding padding padding padding padding padding padding padding.

            12.
            Answer text for question 12 after recovery.
        """).strip()

        parsed = self.a_parser.parse(text, self.offsets)
        # Verify Question 12 parsed successfully after auto-recovery
        paths = [p.hierarchy_path for p in parsed]
        self.assertIn(["12"], paths)

    def test_working_notes_high_number_sequence(self):
        text = textwrap.dedent("""
            Question 6
            Main answer text for question 6.

            Working Notes:
            1. note 1
            2. note 2
            3. note 3
            4. note 4
            5. note 5
            6. note 6
            7. note 7
            8. note 8
            9. note 9
            10. note 10

            7.
            Answer to Question 7 which is a main answer block.
        """).strip()

        parsed = self.a_parser.parse(text, self.offsets)
        paths = [p.hierarchy_path for p in parsed]
        # Verify that only 6 and 7 are validated as top-level answers, 
        # and working notes 1-10 are correctly filtered out as working notes under Question 6
        self.assertIn(["6"], paths)
        self.assertIn(["7"], paths)
        # Verify no working notes got promoted to top-level answers
        self.assertNotIn(["1"], paths)
        self.assertNotIn(["8"], paths)
        self.assertNotIn(["10"], paths)


    def test_promotion_rule_1_question_structure(self):
        # Rule 1: Confirm or reject immediately based on question parser hierarchy if parent has children
        valid_question_paths = {("8",), ("8", "i"), ("8", "ii")}
        
        text = textwrap.dedent("""
            8.
            Some text.
            (a)
            This is sub-answer (a) which should be rejected because it is not in the question structure.
            (i)
            This is sub-answer (i) which should be accepted because it is in the question structure.
            (ii)
            This is sub-answer (ii) which should be accepted because it is in the question structure.
        """).strip()
        
        parsed = self.a_parser.parse(text, self.offsets, valid_question_paths=valid_question_paths)
        paths = [p.hierarchy_path for p in parsed]
        
        self.assertIn(["8"], paths)
        self.assertNotIn(["8", "a"], paths)
        self.assertIn(["8", "i"], paths)
        self.assertIn(["8", "ii"], paths)

    def test_promotion_rule_2_sequence_start(self):
        # Rule 2: Sub-levels must start at 'a' or 'i' when entering a new depth level
        text = textwrap.dedent("""
            10.
            Answer to question 10.
            (b)
            This should be rejected because 'a' was not seen first.
            (ii)
            This should be rejected because 'i' was not seen first.
            (a)
            This should be accepted because it correctly starts the alpha sequence.
            (i)
            This should be accepted because it correctly starts the roman sequence.
        """).strip()
        
        parsed = self.a_parser.parse(text, self.offsets)
        paths = [p.hierarchy_path for p in parsed]
        
        self.assertIn(["10"], paths)
        self.assertNotIn(["10", "b"], paths)
        self.assertNotIn(["10", "ii"], paths)
        self.assertIn(["10", "a"], paths)
        self.assertIn(["10", "a", "i"], paths)

    def test_promotion_rule_3_colon_heuristic(self):
        # Rule 3: Reject candidates preceded by colon if block is structurally list-like (no \n\n, short)
        text = textwrap.dedent("""
            10.
            The adjustments are:
            (a) Relates to asset.
            (b) Relates to liability.
        """).strip()
        
        parsed = self.a_parser.parse(text, self.offsets)
        paths = [p.hierarchy_path for p in parsed]
        
        self.assertIn(["10"], paths)
        self.assertNotIn(["10", "a"], paths)
        self.assertNotIn(["10", "b"], paths)

        # Genuine sub-answers with paragraph breaks should be accepted even if preceded by colon
        text_genuine = textwrap.dedent("""
            10.
            The adjustments are:
            (a)
            This is a genuine long sub-answer because it has multiple lines and contains
            a paragraph break here.
            
            Paragraph two of the sub-answer.
            (b)
            This is second sub-answer.
        """).strip()
        
        parsed_genuine = self.a_parser.parse(text_genuine, self.offsets)
        paths_genuine = [p.hierarchy_path for p in parsed_genuine]
        self.assertIn(["10", "a"], paths_genuine)
        self.assertIn(["10", "b"], paths_genuine)

    def test_promotion_ocr_miss_scenario(self):
        # OCR Miss: valid_question_paths provided but parent 8 has no children registered.
        # Fallback to local sequence / colon checks should identify lists and accept correct sub-answers.
        valid_question_paths = {("8",), ("10",)}
        
        text = textwrap.dedent("""
            8.
            Applying guidance:
            (a)
            Inline list item 1.
            (b)
            Inline list item 2.
            (i)
            Genuine sub-answer 1.
            (ii)
            Genuine sub-answer 2.
        """).strip()
        
        parsed = self.a_parser.parse(text, self.offsets, valid_question_paths=valid_question_paths)
        paths = [p.hierarchy_path for p in parsed]
        
        self.assertIn(["8"], paths)
        # (a) rejected by Rule 3 (colon heuristic)
        self.assertNotIn(["8", "a"], paths)
        # (b) rejected by Rule 2 (sequence start)
        self.assertNotIn(["8", "b"], paths)
        # (i) and (ii) accepted by fallback
        self.assertIn(["8", "i"], paths)
        self.assertIn(["8", "ii"], paths)

    def test_promotion_genuine_without_colon(self):
        # Verify that sub-answers without a preceding colon are promoted normally (Rule 3 doesn't fire)
        text = textwrap.dedent("""
            10.
            Answer text for question 10.
            (a)
            Capital A text block.
            (i)
            Roman numeral text block.
            (b)
            Capital B text block.
        """).strip()
        
        parsed = self.a_parser.parse(text, self.offsets)
        paths = [p.hierarchy_path for p in parsed]
        
        self.assertIn(["10"], paths)
        self.assertIn(["10", "a"], paths)
        self.assertIn(["10", "a", "i"], paths)
        self.assertIn(["10", "b"], paths)

    def test_promotion_colon_with_inline_lists_remains_rejected(self):
        # Verify that inline list items with colon prefix remain rejected (Rule 3 fires)
        text = textwrap.dedent("""
            10.
            The following are:
            (a)
            apple
            (b)
            banana
            11.
            Answer to 11.
        """).strip()
        
        parsed = self.a_parser.parse(text, self.offsets)
        paths = [p.hierarchy_path for p in parsed]
        
        self.assertIn(["10"], paths)
        self.assertNotIn(["10", "a"], paths)
        self.assertNotIn(["10", "b"], paths)
        self.assertIn(["11"], paths)

    def test_promotion_main_question_transition(self):
        # Test transition between main questions when valid_question_paths is provided
        valid_question_paths = {("1",), ("1", "a"), ("2",), ("3",)}
        text = textwrap.dedent("""
            1.
            Answer to 1.
            (a)
            Answer to 1(a).
            2.
            Answer to 2.
            3.
            Answer to 3.
        """).strip()

        parsed = self.a_parser.parse(text, self.offsets, valid_question_paths=valid_question_paths)
        paths = [p.hierarchy_path for p in parsed]

        self.assertIn(["1"], paths)
        self.assertIn(["1", "a"], paths)
        self.assertIn(["2"], paths)
        self.assertIn(["3"], paths)

    def test_mcq_sequence_with_structured_table(self):
        # Test MCQ sequence detection when options are followed by [STRUCTURED_START]
        text = textwrap.dedent("""
            1.
            Question text
            (a) Option A
            (b) Option B
            (c) Option C
            (d) Option D
            [STRUCTURED_START]
            <div class="table-container">| Col 1 | Col 2 |</div>
            [STRUCTURED_END]
        """).strip()

        parsed = self.q_parser.parse(text, self.offsets)
        paths = [p.hierarchy_path for p in parsed]
        # (a), (b), (c), (d) should be detected as MCQ options and not parsed as sub-questions
        self.assertIn(["1"], paths)
        self.assertNotIn(["1", "a"], paths)
        self.assertNotIn(["1", "b"], paths)

    def test_decimal_number_not_matched_as_answer_header(self):
        # Test that decimal numbers (e.g. 14.30, 82.22, 17.95) starting a line are not parsed as answer headers
        text = textwrap.dedent("""
            1.
            Answer text for question 1.
            14.30
            82.22
            17.95%
            583.23 = 0.4650
            2.
            Answer text for question 2.
        """).strip()

        parsed = self.a_parser.parse(text, self.offsets)
        paths = [p.hierarchy_path for p in parsed]

        self.assertIn(["1"], paths)
        self.assertIn(["2"], paths)
        self.assertNotIn(["14"], paths)
        self.assertNotIn(["82"], paths)
        self.assertNotIn(["17"], paths)
        self.assertNotIn(["583"], paths)


if __name__ == "__main__":
    unittest.main()



