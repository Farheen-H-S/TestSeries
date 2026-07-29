from dataclasses import dataclass, field
from enum import Enum
import html
import json
import logging
import re
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

# Type Alias for Bounding Boxes
BBox = Tuple[float, float, float, float]

class CellStyle(Enum):
    NORMAL = "NORMAL"
    BOLD = "BOLD"
    ITALIC = "ITALIC"

class CellAlignment(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"

class MergeConfidence(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class TableAction(Enum):
    DROP_ROW = "DROP_ROW"
    DROP_COLUMN = "DROP_COLUMN"
    MERGE_COLUMNS = "MERGE_COLUMNS"
    MERGE_HEADERS = "MERGE_HEADERS"
    MERGE_PAGES = "MERGE_PAGES"
    CLEAN_GLYPH = "CLEAN_GLYPH"

@dataclass
class Cell:
    text: str
    style: CellStyle = CellStyle.NORMAL
    rowspan: int = 1
    colspan: int = 1
    alignment: CellAlignment = CellAlignment.LEFT
    bbox: Optional[BBox] = None

@dataclass
class Row:
    cells: List[Cell]
    is_header: bool = False
    is_section: bool = False
    is_total: bool = False

@dataclass
class TableProcessingDecision:
    action: TableAction
    details: str
    confidence: Optional[MergeConfidence] = None

@dataclass
class TableDiagnostics:
    removed_columns: int = 0
    removed_rows: int = 0
    merged_columns: int = 0
    merged_tables: int = 0
    header_rows_merged: int = 0
    glyph_replacements: int = 0
    decisions: List[TableProcessingDecision] = field(default_factory=list)

@dataclass
class Table:
    rows: List[Row]
    bbox: Optional[BBox] = None
    page_number: int = 1
    title: str = ""
    page_start: int = 1
    page_end: int = 1
    question: str = ""
    confidence: Optional[MergeConfidence] = None
    original_grid: Optional[List[List[str]]] = None
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ProcessedTable:
    table: Table
    diagnostics: TableDiagnostics

@dataclass
class TableProcessingConfig:
    empty_column_threshold: float = 0.95
    numeric_column_threshold: float = 0.80
    column_coordinate_threshold: float = 15.0
    glyph_map: Dict[str, str] = field(default_factory=lambda: { "`": "₹" })
    page_top_margin: float = 135.0
    page_bottom_margin: float = 707.0  # height (842) - bottom margin (135)
    minimum_table_rows: int = 2


class _CellCleaner:
    """Stage A: Standardizes character encodings, whitespace, and line breaks."""
    def __init__(self, config: TableProcessingConfig, diagnostics: TableDiagnostics):
        self.config = config
        self.diagnostics = diagnostics
        
    def clean(self, grid: List[List[str]]) -> List[List[str]]:
        cleaned_grid = []
        for row in grid:
            cleaned_row = []
            for cell in row:
                if cell is None:
                    cleaned_row.append("")
                    continue
                
                cleaned_text = cell
                
                # Count and replace glyph encoding anomalies
                for anomalous, target in self.config.glyph_map.items():
                    if anomalous in cleaned_text:
                        repl_count = cleaned_text.count(anomalous)
                        self.diagnostics.glyph_replacements += repl_count
                        cleaned_text = cleaned_text.replace(anomalous, target)
                        self.diagnostics.decisions.append(
                            TableProcessingDecision(
                                action=TableAction.CLEAN_GLYPH,
                                details=f"Replaced {repl_count} instance(s) of '{anomalous}' with '{target}'",
                                confidence=MergeConfidence.HIGH
                            )
                        )
                
                # Replace line breaks and normalize space
                cleaned_text = re.sub(r'<br\s*/?>', ' ', cleaned_text, flags=re.IGNORECASE)
                cleaned_text = cleaned_text.replace("\n", " ")
                cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
                cleaned_row.append(cleaned_text.strip())
            cleaned_grid.append(cleaned_row)
        return cleaned_grid


class _StructureNormalizer:
    """Stage B: Grid pruning and alignment cleanup."""
    def __init__(self, config: TableProcessingConfig, diagnostics: TableDiagnostics):
        self.config = config
        self.diagnostics = diagnostics
        
    def drop_empty_rows(self, grid: List[List[str]]) -> List[List[str]]:
        if not grid:
            return grid
        new_grid = []
        for row in grid:
            if any(cell.strip() for cell in row):
                new_grid.append(row)
            else:
                self.diagnostics.removed_rows += 1
                self.diagnostics.decisions.append(
                    TableProcessingDecision(
                        action=TableAction.DROP_ROW,
                        details="Removed completely empty row",
                        confidence=MergeConfidence.HIGH
                    )
                )
        return new_grid
        
    def drop_empty_columns(self, grid: List[List[str]]) -> List[List[str]]:
        if not grid:
            return grid
        num_cols = len(grid[0])
        keep_indices = []
        for col_idx in range(num_cols):
            has_content = False
            for row in grid:
                if col_idx < len(row) and row[col_idx].strip():
                    has_content = True
                    break
            if has_content:
                keep_indices.append(col_idx)
            else:
                self.diagnostics.removed_columns += 1
                self.diagnostics.decisions.append(
                    TableProcessingDecision(
                        action=TableAction.DROP_COLUMN,
                        details=f"Removed empty column at index {col_idx}",
                        confidence=MergeConfidence.HIGH
                    )
                )
                
        new_grid = []
        for row in grid:
            new_row = [row[i] for i in keep_indices]
            new_grid.append(new_row)
        return new_grid

    def merge_columns(self, grid: List[List[str]]) -> List[List[str]]:
        if not grid or len(grid[0]) < 2:
            return grid
            
        num_cols = len(grid[0])
        merged_indices = set()
        
        for j in range(num_cols - 1):
            k = j + 1
            if k in merged_indices or j in merged_indices:
                continue
                
            header_j = grid[0][j].strip()
            header_k = grid[0][k].strip()
            
            # If both have headers, they are distinct company/year columns
            if header_j and header_k:
                continue
                
            data_rows = grid[1:]
            if not data_rows:
                continue
                
            total_data_rows = len(data_rows)
            empty_count_j = sum(1 for row in data_rows if not row[j].strip())
            empty_count_k = sum(1 for row in data_rows if not row[k].strip())
            
            empty_ratio_j = empty_count_j / total_data_rows
            empty_ratio_k = empty_count_k / total_data_rows
            
            one_is_almost_empty = (empty_ratio_j >= self.config.empty_column_threshold) or (empty_ratio_k >= self.config.empty_column_threshold)
            if not one_is_almost_empty:
                continue
                
            both_have_values = any(row[j].strip() and row[k].strip() for row in data_rows)
            if both_have_values:
                continue
                
            one_header_is_empty = (not header_j and header_k) or (header_j and not header_k)
            if not one_header_is_empty:
                continue
                
            empty_col = j if empty_ratio_j >= empty_ratio_k else k
            other_col = k if empty_col == j else j
            non_empty_cells_other = [row[other_col].strip() for row in data_rows if row[other_col].strip()]
            if not non_empty_cells_other:
                continue
                
            numeric_count_other = sum(1 for cell in non_empty_cells_other if re.match(r'^(?:[₹\-\u2013\d,\s\(\)]+|Nil)$', cell))
            numeric_ratio_other = numeric_count_other / len(non_empty_cells_other)
            
            if numeric_ratio_other < self.config.numeric_column_threshold:
                continue
                
            # Merge column k into column j
            for row in grid:
                val_j = row[j].strip()
                val_k = row[k].strip()
                if val_j and val_k:
                    row[j] = val_j + " " + val_k
                elif val_k:
                    row[j] = val_k
                row[k] = ""
            merged_indices.add(k)
            self.diagnostics.merged_columns += 1
            self.diagnostics.decisions.append(
                TableProcessingDecision(
                    action=TableAction.MERGE_COLUMNS,
                    details=f"Merged misaligned columns at indices {j} and {k}",
                    confidence=MergeConfidence.HIGH
                )
            )
            
        new_grid = []
        for row in grid:
            new_row = [row[i] for i in range(num_cols) if i not in merged_indices]
            new_grid.append(new_row)
        return new_grid

    def merge_headers(self, grid: List[List[str]]) -> List[List[str]]:
        if not grid:
            return grid
            
        header_row_count = 0
        for row in grid:
            if not row[0].strip():
                header_row_count += 1
            else:
                break
                
        if header_row_count == 0:
            header_row_count = 1
            
        num_cols = len(grid[0])
        merged_header = []
        for col_idx in range(num_cols):
            cell_parts = []
            for r_idx in range(header_row_count):
                val = grid[r_idx][col_idx].strip()
                if val:
                    cell_parts.append(val)
            joined = " ".join(cell_parts)
            joined = re.sub(r'\s+', ' ', joined).strip()
            merged_header.append(joined)
            
        if not merged_header[0] and any(h.strip() for h in merged_header[1:]):
            merged_header[0] = "Particulars"
            
        self.diagnostics.header_rows_merged = header_row_count
        if header_row_count > 1:
            self.diagnostics.decisions.append(
                TableProcessingDecision(
                    action=TableAction.MERGE_HEADERS,
                    details=f"Merged {header_row_count} header rows",
                    confidence=MergeConfidence.HIGH
                )
            )
            
        new_grid = [merged_header] + grid[header_row_count:]
        return new_grid

    def normalize(self, grid: List[List[str]]) -> List[List[str]]:
        grid = self.drop_empty_rows(grid)
        grid = self.drop_empty_columns(grid)
        grid = self.merge_columns(grid)
        grid = self.merge_headers(grid)
        return grid


def is_header_row_similar(row1: List[Cell], row2: List[Cell]) -> bool:
    if len(row1) != len(row2):
        return False
    matches = 0
    for c1, c2 in zip(row1, row2):
        t1 = c1.text.strip().lower()
        t2 = c2.text.strip().lower()
        if t1 == t2 and t1:
            matches += 1
    return matches >= max(1, len(row1) // 2)

class _CrossPageMerger:
    """Stage C: Coordinates consecutive multi-page table merges."""
    def __init__(self, config: TableProcessingConfig, diagnostics: TableDiagnostics):
        self.config = config
        self.diagnostics = diagnostics
        
    def merge(self, processed_tables: List[ProcessedTable], doc: Any) -> List[ProcessedTable]:
        if not processed_tables:
            return processed_tables
            
        merged_list = []
        for pt in processed_tables:
            table = pt.table
            if not merged_list:
                merged_list.append(pt)
                continue
                
            last_pt = merged_list[-1]
            last_table = last_pt.table
            
            should_merge = False
            reasons = []
            
            # 1. Consecutive pages
            if table.page_number == last_table.page_end + 1:
                # 2. Compatible column layout (same number of columns in row 0)
                if len(table.rows) > 0 and len(last_table.rows) > 0:
                    cols_curr = len(table.rows[0].cells)
                    cols_last = len(last_table.rows[0].cells)
                    if cols_curr == cols_last:
                        # 3. Close horizontal coordinates
                        x0_diff = abs(table.bbox[0] - last_table.bbox[0])
                        x1_diff = abs(table.bbox[2] - last_table.bbox[2])
                        if x0_diff < self.config.column_coordinate_threshold and x1_diff < self.config.column_coordinate_threshold:
                            # 4. Vertical margin boundary check: 
                            # Table A must be near the bottom margin on page N
                            # Table B must be near the top margin on page N+1
                            is_at_bottom_a = (last_table.bbox[3] >= self.config.page_bottom_margin - 30)
                            is_at_top_b = (table.bbox[1] <= self.config.page_top_margin + 30)
                            
                            # 5. Check logical termination of last_table
                            # Does it end with a Total row?
                            last_row_a = last_table.rows[-1]
                            ends_with_total = last_row_a.is_total
                            
                            # 6. Check if table starts with a fresh title header
                            starts_with_title = False
                            first_row_b = table.rows[0]
                            if first_row_b.cells and first_row_b.cells[0].text:
                                text_b = first_row_b.cells[0].text.strip().lower()
                                titles = ["balance sheet", "income statement", "trial balance", "statement of", "profit and loss"]
                                if any(t in text_b for t in titles):
                                    starts_with_title = True
                                    
                            # 7. Check intervening text block check
                            has_intervening_text = False
                            
                            # Page N (0-indexed page number: last_table.page_end - 1)
                            page_n = doc[last_table.page_end - 1]
                            blocks_n = page_n.get_text("blocks")
                            height_n = page_n.rect.height if page_n.rect else 842
                            bottom_margin_n = height_n - 135
                            
                            for b in blocks_n:
                                bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
                                text_val = b[4].strip()
                                # Check if block is below last_table bbox and above margin
                                if by0 > last_table.bbox[3] and by1 < bottom_margin_n:
                                    if text_val:
                                        has_intervening_text = True
                                        break
                                        
                            # Page N+1 (0-indexed page number: table.page_number - 1)
                            if not has_intervening_text:
                                page_np1 = doc[table.page_number - 1]
                                blocks_np1 = page_np1.get_text("blocks")
                                top_margin_np1 = 135
                                for b in blocks_np1:
                                    bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
                                    text_val = b[4].strip()
                                    # Check if block is above table bbox and below margin
                                    if by1 < table.bbox[1] and by0 > top_margin_np1:
                                        if text_val:
                                            has_intervening_text = True
                                            break
                                            
                            if is_at_bottom_a and is_at_top_b and not ends_with_total and not starts_with_title and not has_intervening_text:
                                should_merge = True
                                reasons = [
                                    "consecutive pages",
                                    "compatible column layout",
                                    "close horizontal coordinates",
                                    "vertical page margin continuity",
                                    "no logical termination of previous table",
                                    "no fresh table title",
                                    "no intervening text blocks"
                                ]
                                
            if should_merge:
                # Merge tables!
                start_row_idx = 0
                if is_header_row_similar(table.rows[0].cells, last_table.rows[0].cells):
                    start_row_idx = 1
                    
                last_table.rows.extend(table.rows[start_row_idx:])
                last_table.page_end = table.page_number
                
                # Mark as merged
                table.properties["merged_into"] = f"table_{last_table.page_number}_{last_table.bbox[0]:.1f}_{last_table.bbox[1]:.1f}"
                
                last_table.confidence = MergeConfidence.HIGH
                last_pt.diagnostics.merged_tables += 1
                
                decision_details = f"Merged table from page {table.page_number} into page {last_table.page_start} | Reasons: {', '.join(reasons)}"
                last_pt.diagnostics.decisions.append(
                    TableProcessingDecision(
                        action=TableAction.MERGE_PAGES,
                        details=decision_details,
                        confidence=MergeConfidence.HIGH
                    )
                )
                
                logger.info(
                    "Merged table page %d -> %d | root_table=table_%d_%s | child_table=table_%d_%s | Reasons: %s | Confidence: HIGH",
                    last_table.page_start, table.page_number,
                    last_table.page_start, f"{last_table.bbox[0]:.1f}_{last_table.bbox[1]:.1f}",
                    table.page_number, f"{table.bbox[0]:.1f}_{table.bbox[1]:.1f}",
                    ", ".join(reasons)
                )
                continue
                
            merged_list.append(pt)
            
        return merged_list


class _SemanticAnnotator:
    """Stage D: Identifies headers, section breaks, and totals."""
    def __init__(self, config: TableProcessingConfig, diagnostics: TableDiagnostics):
        self.config = config
        self.diagnostics = diagnostics
        
    def annotate(self, table: Table) -> Table:
        if not table.rows:
            return table
            
        num_cols = len(table.rows[0].cells)
        col_numeric_counts = [0] * num_cols
        col_non_empty_counts = [0] * num_cols
        
        # 1. First scan data rows to compute column alignment signals
        for row in table.rows:
            if row.is_header:
                continue
            for c_idx, cell in enumerate(row.cells):
                if c_idx < len(row.cells) and cell.text.strip():
                    col_non_empty_counts[c_idx] += 1
                    if re.match(r'^(?:[₹\-\u2013\d,\s\(\)]+|Nil)$', cell.text.strip()):
                        col_numeric_counts[c_idx] += 1
                        
        # Determine alignment mapping for each column
        col_alignments = [CellAlignment.LEFT] * num_cols
        for c_idx in range(num_cols):
            non_empty = col_non_empty_counts[c_idx]
            if non_empty > 0:
                ratio = col_numeric_counts[c_idx] / non_empty
                if ratio >= self.config.numeric_column_threshold:
                    col_alignments[c_idx] = CellAlignment.RIGHT
                    
        # 2. Annotate alignments, section rows, and total rows
        for row in table.rows:
            # Set alignment on each cell based on its column alignment
            for c_idx, cell in enumerate(row.cells):
                if c_idx < len(col_alignments):
                    cell.alignment = col_alignments[c_idx]
                    
            if row.is_header:
                continue
                
            first_cell_text = row.cells[0].text.strip()
            # A row is a section row if first column is non-empty and all other columns are empty
            other_cells_empty = all(not cell.text.strip() for cell in row.cells[1:])
            if first_cell_text and other_cells_empty:
                row.is_section = True
                row.cells[0].style = CellStyle.BOLD
                
            # A row is a total row if its first cell text equals "total" (case-insensitive)
            if first_cell_text.lower() == "total":
                row.is_total = True
                
        return table


class _MarkdownSerializer:
    """Stage E1: Serializes the Table model to Markdown representation."""
    @staticmethod
    def serialize(table: Table) -> str:
        if not table.rows:
            return ""
            
        lines = []
        # Find headers
        header_rows = [row for row in table.rows if row.is_header]
        data_rows = [row for row in table.rows if not row.is_header]
        
        if not header_rows:
            dummy_cells = [Cell(text="") for _ in table.rows[0].cells]
            header_row = Row(cells=dummy_cells, is_header=True)
            header_rows = [header_row]
            
        header_row = header_rows[0]
        
        header_parts = []
        for cell in header_row.cells:
            header_parts.append(cell.text)
        lines.append("| " + " | ".join(header_parts) + " |")
        
        lines.append("| " + " | ".join(["---"] * len(header_row.cells)) + " |")
        
        for row in data_rows:
            row_parts = []
            for cell in row.cells:
                text = cell.text
                if text.strip() and (cell.style == CellStyle.BOLD or row.is_section):
                    text = f"**{text}**"
                elif text.strip() and cell.style == CellStyle.ITALIC:
                    text = f"*{text}*"
                row_parts.append(text.replace("|", "\\|"))
            lines.append("| " + " | ".join(row_parts) + " |")
            
        return "\n".join(lines)


class _HTMLRenderer:
    """Stage E2: Renders Table model into clean, styling-ready HTML."""
    @staticmethod
    def render(table: Table) -> str:
        if not table.rows:
            return ""
            
        html_parts = ['<div class="table-container">', '<table class="structured-table">']
        
        has_header = any(row.is_header for row in table.rows)
        
        if has_header:
            html_parts.append('<thead>')
            for row in table.rows:
                if row.is_header:
                    html_parts.append('<tr>')
                    for cell in row.cells:
                        alignment_style = ""
                        if cell.alignment == CellAlignment.RIGHT:
                            alignment_style = ' style="text-align: right;"'
                        elif cell.alignment == CellAlignment.CENTER:
                            alignment_style = ' style="text-align: center;"'
                            
                        bold_start = '<strong>' if cell.style == CellStyle.BOLD else ''
                        bold_end = '</strong>' if cell.style == CellStyle.BOLD else ''
                        html_parts.append(f'<th{alignment_style}>{bold_start}{html.escape(cell.text)}{bold_end}</th>')
                    html_parts.append('</tr>')
            html_parts.append('</thead>')
            
        html_parts.append('<tbody>')
        for row in table.rows:
            if not row.is_header:
                html_parts.append('<tr>')
                for cell in row.cells:
                    alignment_style = ""
                    if cell.alignment == CellAlignment.RIGHT:
                        alignment_style = ' style="text-align: right;"'
                    elif cell.alignment == CellAlignment.CENTER:
                        alignment_style = ' style="text-align: center;"'
                        
                    is_bold = (cell.style == CellStyle.BOLD) or row.is_section or (row.is_total and cell.text)
                    bold_start = '<strong>' if is_bold else ''
                    bold_end = '</strong>' if is_bold else ''
                    
                    html_parts.append(f'<td{alignment_style}>{bold_start}{html.escape(cell.text)}{bold_end}</td>')
                html_parts.append('</tr>')
        html_parts.append('</tbody>')
        
        html_parts.append('</table>')
        html_parts.append('</div>')
        return "".join(html_parts)


class _JSONSerializer:
    """Stage E3: Serializes the Table model to JSON representation."""
    @staticmethod
    def serialize(table: Table) -> str:
        table_dict = {
            "page_number": table.page_number,
            "title": table.title,
            "page_start": table.page_start,
            "page_end": table.page_end,
            "question": table.question,
            "confidence": table.confidence.value if table.confidence else None,
            "properties": table.properties,
            "rows": []
        }
        for row in table.rows:
            row_dict = {
                "is_header": row.is_header,
                "is_section": row.is_section,
                "is_total": row.is_total,
                "cells": []
            }
            for cell in row.cells:
                cell_dict = {
                    "text": cell.text,
                    "style": cell.style.value,
                    "rowspan": cell.rowspan,
                    "colspan": cell.colspan,
                    "alignment": cell.alignment.value,
                    "bbox": cell.bbox
                }
                row_dict["cells"].append(cell_dict)
            table_dict["rows"].append(row_dict)
        return json.dumps(table_dict, indent=2)


class TableProcessor:
    def __init__(self, config: Optional[TableProcessingConfig] = None):
        self.config = config or TableProcessingConfig()
        
    def process(self, raw_grid: List[List[str]], bbox: Optional[BBox] = None, page_number: int = 1) -> ProcessedTable:
        diagnostics = TableDiagnostics()
        
        # Preserve original grid
        original_grid = [[cell for cell in row] for row in raw_grid]
        
        # Stage A: Cell Cleaning
        cleaner = _CellCleaner(self.config, diagnostics)
        grid = cleaner.clean(raw_grid)
        
        # Stage B: Structural Normalization
        normalizer = _StructureNormalizer(self.config, diagnostics)
        grid = normalizer.normalize(grid)
        
        if not grid:
            table = Table(
                rows=[],
                bbox=bbox,
                page_number=page_number,
                page_start=page_number,
                page_end=page_number,
                original_grid=original_grid
            )
            return ProcessedTable(table=table, diagnostics=diagnostics)
            
        rows = []
        for idx, row in enumerate(grid):
            cells = []
            for cell_text in row:
                cells.append(Cell(text=cell_text))
                
            is_header = (idx == 0)
            rows.append(Row(cells=cells, is_header=is_header))
            
        table = Table(
            rows=rows,
            bbox=bbox,
            page_number=page_number,
            page_start=page_number,
            page_end=page_number,
            original_grid=original_grid
        )
        
        # Stage D: Semantic Annotation
        annotator = _SemanticAnnotator(self.config, diagnostics)
        table = annotator.annotate(table)
        
        return ProcessedTable(table=table, diagnostics=diagnostics)

    def merge_cross_page_tables(self, processed_tables: List[ProcessedTable], doc: Any) -> List[ProcessedTable]:
        """Stage C: Merges consecutive split tables across pages."""
        # Using a dummy TableDiagnostics for page merging diagnostics orchestration
        merger = _CrossPageMerger(self.config, TableDiagnostics())
        return merger.merge(processed_tables, doc)

    @staticmethod
    def serialize_to_markdown(table: Table) -> str:
        """Stage E1: Serializes Table model to Markdown representation."""
        return _MarkdownSerializer.serialize(table)

    @staticmethod
    def render_to_html(table: Table) -> str:
        """Stage E2: Renders Table model to HTML representation."""
        return _HTMLRenderer.render(table)

    @staticmethod
    def serialize_to_json(table: Table) -> str:
        """Stage E3: Serializes Table model to structured JSON representation."""
        return _JSONSerializer.serialize(table)


def parse_markdown_to_table(markdown_table: str) -> Table:
    lines = [line.strip() for line in markdown_table.strip().split('\n') if line.strip()]
    if not lines:
        return Table(rows=[])
    
    rows = []
    has_header = False
    
    for line in lines:
        if line.startswith('|') and line.endswith('|'):
            cells_raw = [cell.strip() for cell in line.split('|')[1:-1]]
            
            if all(re.match(r'^[-:]+$', cell) for cell in cells_raw):
                continue
                
            cells = []
            for cell_text in cells_raw:
                style = CellStyle.NORMAL
                clean_text = cell_text
                
                if cell_text.startswith('**') and cell_text.endswith('**') and len(cell_text) > 4:
                    style = CellStyle.BOLD
                    clean_text = cell_text[2:-2].strip()
                elif cell_text.startswith('*') and cell_text.endswith('*') and len(cell_text) > 2:
                    style = CellStyle.ITALIC
                    clean_text = cell_text[1:-1].strip()
                    
                alignment = CellAlignment.LEFT
                if clean_text and re.match(r'^(?:[₹\-\u2013\d,\s\(\)]+|Nil)$', clean_text.strip()):
                    alignment = CellAlignment.RIGHT
                    
                cells.append(Cell(text=clean_text, style=style, alignment=alignment))
                
            is_header = not has_header
            is_section = False
            is_total = False
            
            if is_header:
                has_header = True
            else:
                if cells[0].text and not any(c.text.strip() for c in cells[1:]):
                    is_section = True
                    cells[0].style = CellStyle.BOLD
                if cells[0].text.strip().lower() == "total":
                    is_total = True
                    
            rows.append(Row(cells=cells, is_header=is_header, is_section=is_section, is_total=is_total))
            
    table = Table(rows=rows)
    annotator = _SemanticAnnotator(TableProcessingConfig(), TableDiagnostics())
    table = annotator.annotate(table)
    return table
