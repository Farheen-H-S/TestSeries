import fitz
from django.test import TestCase
from unittest.mock import MagicMock
from ..services.table_processing import (
    TableProcessor,
    TableProcessingConfig,
    Cell,
    Row,
    CellStyle,
    CellAlignment,
    MergeConfidence,
    TableAction,
    parse_markdown_to_table
)

class TableProcessingTests(TestCase):
    def setUp(self):
        self.config = TableProcessingConfig()
        self.processor = TableProcessor(self.config)

    def test_cell_cleaner_glyph_replacement(self):
        # Setup table with backtick anomalies
        raw_grid = [
            ["Particulars", "M Ltd.`", "N Ltd."],
            ["Property, Plant ` Equipment", "6,50,000", "4,05,000"]
        ]
        pt = self.processor.process(raw_grid)
        table = pt.table
        
        # Check glyph mapping replaced backticks with rupees
        self.assertEqual(table.rows[0].cells[1].text, "M Ltd.₹")
        self.assertEqual(table.rows[1].cells[0].text, "Property, Plant ₹ Equipment")
        self.assertEqual(pt.diagnostics.glyph_replacements, 2)

    def test_cell_cleaner_whitespace_normalization(self):
        # Setup table with extra spaces and newlines
        raw_grid = [
            [" Particulars ", "M\nLtd."],
            ["Property,  Plant  Equipment", "6,50,000<br/>"]
        ]
        pt = self.processor.process(raw_grid)
        table = pt.table
        
        self.assertEqual(table.rows[0].cells[0].text, "Particulars")
        self.assertEqual(table.rows[0].cells[1].text, "M Ltd.")
        self.assertEqual(table.rows[1].cells[0].text, "Property, Plant Equipment")
        self.assertEqual(table.rows[1].cells[1].text, "6,50,000")

    def test_drop_empty_rows_and_columns(self):
        # Setup table with completely empty row and column
        raw_grid = [
            ["Particulars", "", "M Ltd."],
            ["", "", ""],
            ["Property, Plant & Equipment", "", "6,50,000"]
        ]
        pt = self.processor.process(raw_grid)
        table = pt.table
        
        # The empty column at index 1 and empty row at index 1 should be dropped
        # Resulting table should be 2x2
        self.assertEqual(len(table.rows), 2)
        self.assertEqual(len(table.rows[0].cells), 2)
        self.assertEqual(table.rows[0].cells[0].text, "Particulars")
        self.assertEqual(table.rows[0].cells[1].text, "M Ltd.")
        self.assertEqual(table.rows[1].cells[0].text, "Property, Plant & Equipment")
        self.assertEqual(table.rows[1].cells[1].text, "6,50,000")
        self.assertEqual(pt.diagnostics.removed_rows, 1)
        self.assertEqual(pt.diagnostics.removed_columns, 1)

    def test_merge_columns_safeguards(self):
        # Setup table where Col 1 is empty in data, Col 2 has no header but has data
        raw_grid = [
            ["Particulars", "N Ltd. (As on 31.12.20X1)", ""],
            ["Property, Plant & Equipment", "", "4,05,000"],
            ["Inventory", "", "3,50,000"]
        ]
        pt = self.processor.process(raw_grid)
        table = pt.table
        
        # Col 1 and Col 2 should be merged!
        self.assertEqual(len(table.rows[0].cells), 2)
        self.assertEqual(table.rows[0].cells[1].text, "N Ltd. (As on 31.12.20X1)")
        self.assertEqual(table.rows[1].cells[1].text, "4,05,000")
        self.assertEqual(table.rows[2].cells[1].text, "3,50,000")
        self.assertEqual(pt.diagnostics.merged_columns, 1)

    def test_merge_columns_safeguards_both_headers_present(self):
        # Should NOT merge if both have headers
        raw_grid = [
            ["Particulars", "M Ltd.", "N Ltd."],
            ["Property, Plant & Equipment", "6,50,000", ""],
            ["Inventory", "2,00,000", ""]
        ]
        pt = self.processor.process(raw_grid)
        table = pt.table
        
        # Column count remains 3 because both headers are present
        self.assertEqual(len(table.rows[0].cells), 3)

    def test_merge_multi_row_headers(self):
        # Setup multi-row headers
        raw_grid = [
            ["", "M Ltd.", "N Ltd."],
            ["", "(As on 31.3.20X2)", "(As on 31.12.20X1)"],
            ["ASSETS", "", ""],
            ["Property, Plant & Equipment", "6,50,000", "4,05,000"]
        ]
        pt = self.processor.process(raw_grid)
        table = pt.table
        
        # First cell is empty in row 0 and row 1, so they are merged into row 0
        # Data rows start from ASSETS (index 1 in processed table)
        self.assertEqual(len(table.rows), 3)
        self.assertEqual(table.rows[0].cells[0].text, "Particulars") # Default Particulars
        self.assertEqual(table.rows[0].cells[1].text, "M Ltd. (As on 31.3.20X2)")
        self.assertEqual(table.rows[0].cells[2].text, "N Ltd. (As on 31.12.20X1)")
        
        # ASSETS is section row
        self.assertTrue(table.rows[1].is_section)
        self.assertEqual(table.rows[1].cells[0].text, "ASSETS")

    def test_semantic_annotations(self):
        # Setup table to test section headers, totals, and column alignments
        raw_grid = [
            ["Particulars", "M Ltd.", "N Ltd."],
            ["ASSETS", "", ""],
            ["Property, Plant & Equipment", "6,50,000", "4,05,000"],
            ["Total", "6,50,000", "4,05,000"]
        ]
        pt = self.processor.process(raw_grid)
        table = pt.table
        
        # ASSETS should be section header and bold
        self.assertTrue(table.rows[1].is_section)
        self.assertEqual(table.rows[1].cells[0].style, CellStyle.BOLD)
        
        # Total should be total row
        self.assertTrue(table.rows[3].is_total)
        
        # Columns 1 and 2 should be right aligned (numeric)
        self.assertEqual(table.rows[2].cells[0].alignment, CellAlignment.LEFT)
        self.assertEqual(table.rows[2].cells[1].alignment, CellAlignment.RIGHT)
        self.assertEqual(table.rows[2].cells[2].alignment, CellAlignment.RIGHT)

    def test_markdown_and_html_rendering_parity(self):
        # Test markdown serialization and HTML rendering parity
        raw_grid = [
            ["Particulars", "M Ltd.", "N Ltd."],
            ["ASSETS", "", ""],
            ["Property, Plant & Equipment", "6,50,000", "4,05,000"],
            ["Total", "6,50,000", "4,05,000"]
        ]
        pt = self.processor.process(raw_grid)
        table = pt.table
        
        markdown_str = TableProcessor.serialize_to_markdown(table)
        html_str = TableProcessor.render_to_html(table)
        
        # Verify markdown bolding is applied to section rows
        self.assertIn("| **ASSETS** |  |  |", markdown_str)
        
        # Deserialize markdown back to Table
        deserialized_table = parse_markdown_to_table(markdown_str)
        deserialized_html_str = TableProcessor.render_to_html(deserialized_table)
        
        # Ensure deserialized HTML matches original HTML
        self.assertEqual(deserialized_html_str, html_str)
        self.assertIn("<strong>ASSETS</strong>", html_str)

    def test_evaluate_structural_reliability(self):
        from ..services.table_processing import evaluate_structural_reliability
        
        # Simple reliable table
        simple_grid = [
            ["Particulars", "Amount"],
            ["Item A", "100"],
            ["Item B", "200"]
        ]
        self.assertTrue(evaluate_structural_reliability(simple_grid))

        # Complex table with merged header keywords (e.g. Balance Sheet)
        complex_grid = [
            ["Particulars Note No.", "Amount (Rs.)", "Amount (Rs.)", "Amount (Rs.)"],
            ["A.", "Non-Current Assets", "", ""],
            ["", "1.", "Property, Plant and Equipment", "10,55,000"]
        ]
        self.assertFalse(evaluate_structural_reliability(complex_grid))

    def test_visual_object_html_rendering_with_provenance(self):
        from ..services.table_processing import Table, _HTMLRenderer
        
        table = Table(rows=[])
        table.properties["is_complex"] = True
        table.page_start = 42
        table.page_end = 43
        table.properties["regions"] = [
            {"page_number": 42, "bbox": [10.0, 20.0, 500.0, 400.0], "crop_path": "media/table_crops/doc1_p42_y20.png"},
            {"page_number": 43, "bbox": [10.0, 20.0, 500.0, 300.0], "crop_path": "media/table_crops/doc1_p43_y20.png"}
        ]
        
        rendered_html = _HTMLRenderer.render(table)
        self.assertIn('data-is-complex="true"', rendered_html)
        self.assertIn('data-table-provenance=', rendered_html)
        self.assertIn('doc1_p42_y20.png', rendered_html)
        self.assertIn('doc1_p43_y20.png', rendered_html)
        self.assertIn('class="table-visual-region"', rendered_html)

