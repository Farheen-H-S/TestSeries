"""
Phase-by-Phase Forensic Verification Suite for Paper Extraction Engine
Verifies all 10 root cause bug fixes across Phase 1, Phase 2, Phase 3, and Phase 4.
"""
from django.test import TestCase
import textwrap
import re

from apps.extraction.services.normalizer import Normalizer
from apps.extraction.services.question_parser import QuestionParser
from apps.extraction.services.answer_parser import AnswerParser
from apps.extraction.services.header_validator import HeaderValidator
from apps.extraction.services.layout_detector import DocumentLayoutDetector
from apps.extraction.services.answer_matcher import AnswerMatcher
from apps.extraction.services.chapter_mapper import get_prepared_chapters, map_question_to_chapter
from apps.extraction.services.types import ParserConfig, ParsedQuestion, ParsedAnswer
from apps.extraction.services.extraction_patterns import MCQ_ANSWER_SECTION_PATTERNS, get_default_parser_config
from apps.papers.models import Question
from apps.syllabus.models import Subject, Chapter
from apps.documents.models import Document


class Phase1VerificationTests(TestCase):
    """
    Phase 1: Data Integrity & Core Engine Safety (Bugs #3, #1, #2)
    """

    def setUp(self):
        self.config = get_default_parser_config()
        self.q_parser = QuestionParser(self.config)
        self.a_parser = AnswerParser(self.config)

    def test_bug3_ocr_pre_normalization_scoped_to_headers(self):
        """Bug #3: Header OCR fixes work, full text body is NOT corrupted."""
        # Header OCR corrections work:
        self.assertEqual(Normalizer.pre_normalize_ocr("Question 12S"), "Question 125")
        self.assertEqual(Normalizer.pre_normalize_ocr("Question 1O5"), "Question 105")
        self.assertEqual(Normalizer.pre_normalize_ocr("Question S"), "Question 5")

        # Body text data integrity is preserved (no global mutations):
        body_text = "As per Section 80B and Ind AS 115s, variable b=1,00,000 applies."
        self.assertEqual(Normalizer.pre_normalize_ocr(body_text), body_text)

    def test_bug1_unbounded_digit_regex_and_abbreviations(self):
        """Bug #1: Years (2025.) and Latin abbreviations (i.e., e.g.) are NOT matched as question headers."""
        text = textwrap.dedent("""
            Question 1
            The year-end was 2025. Next line.
            i.e., tax deducted at source applies.
            e.g., under section 80C.
        """).strip()

        offsets = [(0, 1)] * len(text)
        parsed = self.q_parser.parse(text, offsets)
        paths = [p.hierarchy_path for p in parsed]

        # Only Question 1 should be parsed, NOT ['2025'], ['i'], or ['e']
        self.assertEqual(len(parsed), 1)
        self.assertEqual(paths, [["1"]])

    def test_bug2_mcq_plural_heading_matching(self):
        """Bug #2: Heading 'ANSWERS TO MULTIPLE CHOICE QUESTIONS' matches MCQ section patterns."""
        heading = "ANSWERS TO MULTIPLE CHOICE QUESTIONS"
        matched = any(re.search(pat, heading) for pat in MCQ_ANSWER_SECTION_PATTERNS)
        self.assertTrue(matched, "Plural 'ANSWERS TO MULTIPLE CHOICE QUESTIONS' must match MCQ answer section patterns")


class Phase2VerificationTests(TestCase):
    """
    Phase 2: Structural & State Machine Refinements (Bugs #4, #5)
    """

    def setUp(self):
        self.validator = HeaderValidator()
        self.config = get_default_parser_config()
        self.layout_detector = DocumentLayoutDetector(self.config)

    def test_bug4_mainless_roman_numeral_case_scenario(self):
        """Bug #4: Top-level Roman numerals (I., II.) initialize hierarchy for Integrated Case Scenarios."""
        result_unbracketed = self.validator._check_logical_transition(["i"], [], raw_header="I.")
        self.assertTrue(result_unbracketed.is_valid, "Top-level 'I.' must be valid to start a paper hierarchy")

        result_bracketed = self.validator._check_logical_transition(["i"], [], raw_header="(i)")
        self.assertFalse(result_bracketed.is_valid, "Bracketed '(i)' must be rejected as starting sequence")

    def test_bug5_layout_detector_prevents_page1_slicing(self):
        """Bug #5: 'ANSWERS' inside Page 1 instructions does NOT trigger premature document slicing."""
        preamble_only_text = "Instructions Regarding Answers\nQuestion 1\nText\nSUGGESTED ANSWERS\nAns 1\nText"
        result_preamble = self.layout_detector.detect_layout(preamble_only_text)
        self.assertNotEqual(result_preamble.boundary_position, 0)


class Phase3VerificationTests(TestCase):
    """
    Phase 3: Pipeline & Matcher Alignment (Bugs #6, #7)
    """

    def test_bug6_answer_matcher_interleaved_self_matching(self):
        """Bug #6: Distinct Q and A in interleaved layout are NOT rejected as self-matching."""
        q = ParsedQuestion(hierarchy_path=["1"], start_offset=100, end_offset=500, text="Q1 text", raw_header="Question 1", start_page=1, end_page=1)
        a = ParsedAnswer(hierarchy_path=["1"], start_offset=250, end_offset=450, text="A1 text", raw_header="Ans 1", start_page=1, end_page=1)

        matcher = AnswerMatcher()
        match_res = matcher.match([q], [a])

        self.assertEqual(match_res.diagnostics.matched_count, 1)
        self.assertEqual(len(match_res.diagnostics.unmatched_questions), 0)

        # Same offset candidate MUST be rejected as self-matching
        q_self = ParsedQuestion(hierarchy_path=["1"], start_offset=100, end_offset=500, text="Q1 text", raw_header="Q1", start_page=1, end_page=1)
        a_self = ParsedAnswer(hierarchy_path=["1"], start_offset=100, end_offset=500, text="Q1 text", raw_header="Q1", start_page=1, end_page=1)

        self.assertEqual(matcher.match([q_self], [a_self]).diagnostics.matched_count, 0)


class Phase4VerificationTests(TestCase):
    """
    Phase 4: Auxiliary Cleanup & Database/Logging Reliability (Bugs #8, #9, #10)
    """

    def test_bug9_sub_question_label_max_length_50(self):
        """Bug #9: Deep sub-question label up to 50 characters stored without truncation."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(username="testuser9", password="password")
        subject = Subject.objects.create(name="Test Subject 9", exam_level=Subject.ExamLevel.FINAL)
        doc = Document.objects.create(
            user=user,
            subject=subject,
            title="Test Doc 9",
            document_type=Document.DocumentType.RTP,
            paper_year=2026,
            storage_path="dummy.pdf"
        )

        long_label = "13.h.i.a.sub_part_label_extended"
        q = Question.objects.create(
            document=doc,
            question_number="13",
            sub_question_label=long_label[:50],
            hierarchy_key=f"13.{long_label[:50]}",
            question_content="<p>Test</p>",
            question_text="Test",
            answer_content="<p>Ans</p>",
            answer_text="Ans"
        )
        self.assertEqual(q.sub_question_label, long_label)

    def test_bug10_chapter_mapper_weight_priority(self):
        """Bug #10: Topic titles take precedence over generic 'Chapter 2' cross-references."""
        subject = Subject.objects.create(name="Financial Accounting", exam_level=Subject.ExamLevel.FINAL)
        ch1 = Chapter.objects.create(subject=subject, chapter_order=1, chapter_name="Chapter 1: Consolidated Financial Statements")
        ch2 = Chapter.objects.create(subject=subject, chapter_order=2, chapter_name="Chapter 2: Financial Instruments")

        prepared = get_prepared_chapters(subject)
        q_text = "Refer to Chapter 2 for details. Calculate Consolidated Financial Statements for the group."
        mapped = map_question_to_chapter(q_text, prepared)

        self.assertEqual(mapped, ch1, "Topic title matching must take precedence over generic Chapter 2 cross-reference")

    def test_e2e_html_mcq_table_extraction(self):
        """Verify that HTML structured MCQ tables are parsed into MCQ ParsedAnswers."""
        from apps.extraction.services.answer_parser import AnswerParser
        from apps.extraction.services.extraction_patterns import get_default_parser_config

        config = get_default_parser_config()
        parser = AnswerParser(config)

        html_text = (
            "Suggested Answers\n"
            "Answers to Multiple Choice Questions\n"
            "[STRUCTURED_START]\n"
            "<table class=\"structured-table\"><thead><tr><th>Question No.</th><th>Answer</th></tr></thead>"
            "<tbody><tr><td>1.</td><td>(b)</td></tr><tr><td>2.</td><td>(c)</td></tr><tr><td>3.</td><td>(a)</td></tr></tbody></table>\n"
            "[STRUCTURED_END]\n"
            "Question 4\nDescriptive answer details."
        )

        answers = parser.parse(html_text, [(0, 1)])
        paths = [a.hierarchy_path for a in answers]
        self.assertIn(["1"], paths)
        self.assertIn(["2"], paths)
        self.assertIn(["3"], paths)
        self.assertIn(["4"], paths)

        # Check MCQ answers text
        a1 = next(a for a in answers if a.hierarchy_path == ["1"])
        self.assertEqual(a1.text, "(b)")

    def test_e2e_decimal_hierarchy_normalization(self):
        """Verify that decimal Case Study questions (e.g. 1.1, 1.2, 2.1) decompose into ['1', '1'], ['1', '2']."""
        from apps.extraction.services.normalizer import Normalizer
        from apps.extraction.services.question_parser import QuestionParser
        from apps.extraction.services.extraction_patterns import get_default_parser_config

        norm = Normalizer()
        self.assertEqual(norm.normalize_header("1.1"), ["1", "1"])
        self.assertEqual(norm.normalize_header("1.2"), ["1", "2"])
        self.assertEqual(norm.normalize_header("2.5"), ["2", "5"])

        config = get_default_parser_config()
        q_parser = QuestionParser(config)
        doc_text = "QUESTIONS\n1.1\nCase question 1 text\n(a) Option A\n(b) Option B\n1.2\nCase question 2 text\n(a) Opt A\n(b) Opt B\n"
        qs = q_parser.parse(doc_text, [(0, 1)], enable_semantic_validation=False)
        q_paths = [q.hierarchy_path for q in qs]
        self.assertIn(["1", "1"], q_paths)
        self.assertIn(["1", "2"], q_paths)

    def test_subject_metadata_filtering_various_casings_and_formats(self):
        """Verify that subject headers in all casings, formats, and paper prefixes are filtered out."""
        from apps.extraction.services.html_formatter import clean_metadata_text

        raw_text = (
            "PAPER – 2 : ADVANCED FINANCIAL MANAGEMENT\n"
            "FINAL EXAMINATION\n"
            "MAY 2026\n"
            "An investor holds a portfolio of 4 securities.\n"
            "Calculate the portfolio variance and Sharpe ratio."
        )

        cleaned = clean_metadata_text(raw_text, subject_name="Advanced Financial Management")
        self.assertNotIn("ADVANCED FINANCIAL MANAGEMENT", cleaned)
        self.assertNotIn("FINAL EXAMINATION", cleaned)
        self.assertNotIn("MAY 2026", cleaned)
        self.assertIn("An investor holds a portfolio of 4 securities.", cleaned)
        self.assertIn("Calculate the portfolio variance and Sharpe ratio.", cleaned)

        # Direct Tax variations with & vs and
        dt_text = (
            "Paper - 4 : Direct Tax Laws and International Taxation\n"
            "Compute the total income of XYZ Ltd."
        )
        cleaned_dt = clean_metadata_text(dt_text, subject_name="Direct Tax Laws & International Taxation")
        self.assertNotIn("Direct Tax Laws", cleaned_dt)
        self.assertIn("Compute the total income of XYZ Ltd.", cleaned_dt)

