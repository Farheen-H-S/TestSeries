import pymupdf as fitz
from django.test import TestCase
from unittest.mock import MagicMock
from ..services.text_extractor import (
    find_standalone_equation_regions,
    normalize_text_glyphs,
    extract_text,
    PUA_SYMBOL_MAP
)

class EquationProcessingTests(TestCase):
    def test_normalize_text_glyphs_pua_symbols(self):
        text = "\uf0732P = (0.52 x 167.75) + \uf062_D + \uf06d_port"
        cleaned = normalize_text_glyphs(text)
        self.assertIn("σ", cleaned)
        self.assertIn("β", cleaned)
        self.assertIn("μ", cleaned)
        self.assertNotIn("\uf073", cleaned)
        self.assertNotIn("\uf062", cleaned)

    def test_normalize_text_glyphs_rupee_symbol(self):
        text = "Sold receivables for ` 100 million at ` 350 each."
        cleaned = normalize_text_glyphs(text)
        self.assertIn("₹ 100 million", cleaned)
        self.assertIn("₹ 350", cleaned)
        self.assertNotIn("` 100", cleaned)

    def test_find_standalone_equation_regions_skips_tables(self):
        # Create a mock page where block is inside table bbox
        page = MagicMock()
        page.get_text.return_value = {
            "blocks": [
                {
                    "bbox": (100, 200, 300, 250),
                    "lines": [
                        {"spans": [{"text": "σ"}]},
                        {"spans": [{"text": "-"}]},
                        {"spans": [{"text": "β"}]},
                        {"spans": [{"text": "2"}]},
                    ]
                }
            ]
        }
        table_bboxes = [(90, 190, 310, 260)] # Encloses the block
        regions = find_standalone_equation_regions(page, table_bboxes)
        self.assertEqual(len(regions), 0)

    def test_find_standalone_equation_regions_detects_fragmented_formula(self):
        # Create a mock page where block is standalone and heavily fragmented
        page = MagicMock()
        page.rect = fitz.Rect(0, 0, 595, 842)
        page.get_text.return_value = {
            "blocks": [
                {
                    "bbox": (100, 200, 300, 220), # 20pt height with 6 short lines = high density
                    "lines": [
                        {"spans": [{"text": "AX"}]},
                        {"spans": [{"text": "2"}]},
                        {"spans": [{"text": "X"}]},
                        {"spans": [{"text": "ov."}]},
                        {"spans": [{"text": "C"}]},
                        {"spans": [{"text": "-"}]},
                    ]
                }
            ]
        }
        table_bboxes = []
        regions = find_standalone_equation_regions(page, table_bboxes)
        self.assertEqual(len(regions), 1)

    def test_find_standalone_equation_regions_ignores_normal_prose(self):
        # Create a mock page with standard long text lines
        page = MagicMock()
        page.rect = fitz.Rect(0, 0, 595, 842)
        page.get_text.return_value = {
            "blocks": [
                {
                    "bbox": (100, 200, 500, 300), # 100pt height with 4 long sentences
                    "lines": [
                        {"spans": [{"text": "The company reported a net profit margin of fifteen percent during the financial year."}]},
                        {"spans": [{"text": "Revenue from operations grew substantially across all core business divisions."}]},
                        {"spans": [{"text": "Management expects continued growth in the upcoming quarterly reporting periods."}]},
                        {"spans": [{"text": "Total assets and liabilities remained stable with adequate debt service coverage."}]},
                    ]
                }
            ]
        }
        table_bboxes = []
        regions = find_standalone_equation_regions(page, table_bboxes)
        self.assertEqual(len(regions), 0)
