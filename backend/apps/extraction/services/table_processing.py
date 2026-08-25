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
                # Safeguard: check if candidate row contains an Option answer choice (meaning it is data, not header)
                is_data = False
                for cell in row[1:]:
                    text = cell.strip() if cell else ""
                    if text and re.match(r'(?i)^Option\s*\([a-e]\)', text):
                        is_data = True
                        break
                if is_data:
                    break
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

def evaluate_structural_reliability(raw_grid: List[List[str]]) -> bool:
    """
    Evaluates whether an extracted table grid can be reliably reconstructed into clean HTML.
    Returns True if structurally reliable, False if unreliable/complex (requiring source PDF visual crop).
    """
    if not raw_grid or len(raw_grid) < 2:
        return True
        
    hdr_str = ' '.join(str(c or '') for c in raw_grid[0])
    
    # Check 1: Known complex merged headers / balance sheet structural anomalies
    merged_header_keywords = [
        'particulars note', 'opening carrying', 'closing carrying', 
        'non-current', 'equity and', 'consolidated balance', 
        'statement of profit', 'carrying amount'
    ]
    if any(k in hdr_str.lower() for k in merged_header_keywords):
        return False
        
    # Check 2: PyMuPDF dummy column placeholders ('Col1', 'Col2')
    if any(re.search(r'\bCol\d+\b', str(c or ''), re.IGNORECASE) for row in raw_grid for c in row):
        return False

    # Check 3: Staggered leading offset column detection (e.g. empty col 0 with item numbers in col 1)
    col0_empty_count = sum(1 for r in raw_grid[1:] if len(r) > 1 and not (r[0] or '').strip() and (r[1] or '').strip())
    non_empty_data_rows = len(raw_grid) - 1
    if non_empty_data_rows > 0 and (col0_empty_count / non_empty_data_rows) >= 0.4:
        # Preserve tables that are simple MCQ answer key listings
        is_mcq_table = any(
            re.search(r'(?i)\bOption\b|\([a-eA-E]\)|\bAns\.?\b', str(cell or ''))
            for row in raw_grid for cell in row
        )
        if not is_mcq_table:
            return False

    # Check 4: Extreme column count variation across rows
    col_counts = [len(r) for r in raw_grid if any(str(c or '').strip() for c in r)]
    if col_counts:
        max_c = max(col_counts)
        min_c = min(col_counts)
    return True


def is_narrative_text_box(grid: List[List[str]]) -> bool:
    """
    Detects whether an extracted table grid from PyMuPDF is actually a bordered
    callout box, decorative banner, or narrative paragraph rather than a true data table.
    """
    if not grid or not grid[0]:
        return True
    
    all_text = ' '.join(str(c or '').strip() for r in grid for c in r if str(c or '').strip())
    if not all_text:
        return True
        
    # Exclude title banner headers
    if re.search(r'(?i)\b(?:REVISION\s+TEST\s+PAPERS?|FINAL\s+EXAMINATION|PAPER\s*[-–—:]?\s*\d+)\b', all_text):
        return True
        
    # Check if table contains tabular financial/accounting headers, currencies, or column indicators
    has_table_signals = bool(re.search(
        r'(?i)(?:\b(?:Particulars|Amount|Debit|Credit|Date|Account|Balance|Assets?|Liabilities|Shares?|Ratio|TDS|TCS|GST|Total|Quantity|Rate|Units?|Ledger)\b|[`₹$]|Rs\.)',
        all_text
    ))
    if has_table_signals:
        return False

    is_mcq_key = bool(re.search(r'(?i)\bOption\b|\bAns\.?\b|\bChoice\b|\bKey\b', all_text))
    has_digits = bool(re.search(r'\d', all_text))
    if not has_table_signals and not has_digits and not is_mcq_key:
        return True

    total_non_empty_cells = 0
    non_empty_rows = 0
    multi_cell_rows = 0
    for r in grid:
        non_empty_in_row = sum(1 for c in r if str(c or '').strip())
        if non_empty_in_row > 0:
            non_empty_rows += 1
            total_non_empty_cells += non_empty_in_row
            if non_empty_in_row >= 2:
                multi_cell_rows += 1
    if non_empty_rows == 0:
        return True

    if multi_cell_rows == 0 and not is_mcq_key:
        return True
    if multi_cell_rows / non_empty_rows < 0.4 and not is_mcq_key:
        if any(len(str(c or '').strip()) > 50 for r in grid for c in r):
            return True
    if len(grid) == 1 and not is_mcq_key:
        if len(all_text) > 40:
            return True
    return False


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
                    if cols_curr != cols_last:
                        logger.info(
                            "Rejected merging tables split between page %d and %d: Column count mismatch (%d vs %d) | Confidence: LOW",
                            last_table.page_end, table.page_number, cols_last, cols_curr
                        )
                    else:
                        # 3. Close horizontal coordinates
                        x0_diff = abs(table.bbox[0] - last_table.bbox[0])
                        x1_diff = abs(table.bbox[2] - last_table.bbox[2])
                        if x0_diff >= self.config.column_coordinate_threshold or x1_diff >= self.config.column_coordinate_threshold:
                            logger.info(
                                "Rejected merging tables split between page %d and %d: Bounding box misalignment (x0 diff: %s, x1 diff: %s) | Confidence: LOW",
                                last_table.page_end, table.page_number, f"{x0_diff:.1f}", f"{x1_diff:.1f}"
                            )
                        else:
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
                                            
                            if not is_at_bottom_a or not is_at_top_b:
                                logger.info(
                                    "Rejected merging tables split between page %d and %d: Table not adjacent to page margins (A bottom: %s, B top: %s) | Confidence: LOW",
                                    last_table.page_end, table.page_number, f"{last_table.bbox[3]:.1f}", f"{table.bbox[1]:.1f}"
                                )
                            elif ends_with_total:
                                logger.info(
                                    "Rejected merging tables split between page %d and %d: Prior table ends with a Total row | Confidence: LOW",
                                    last_table.page_end, table.page_number
                                )
                            elif starts_with_title:
                                logger.info(
                                    "Rejected merging tables split between page %d and %d: Subsequent table starts with a new title heading | Confidence: LOW",
                                    last_table.page_end, table.page_number
                                )
                            elif has_intervening_text:
                                logger.info(
                                    "Rejected merging tables split between page %d and %d: Intervening non-margin text blocks detected | Confidence: LOW",
                                    last_table.page_end, table.page_number
                                )
                            else:
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
                
                # Merge visual regions provenance
                curr_regions = table.properties.get("regions", [])
                if "regions" not in last_table.properties:
                    last_table.properties["regions"] = []
                for r in curr_regions:
                    if r not in last_table.properties["regions"]:
                        last_table.properties["regions"].append(r)
                        
                # Multi-page merged tables are visual-object targets for PDF presentation
                last_table.properties["is_complex"] = True
                
                # Mark as merged
                table.properties["merged_into"] = f"table_{last_table.page_number}_{last_table.bbox[0]:.1f}_{last_table.bbox[1]:.1f}"
                
                last_table.confidence = MergeConfidence.HIGH
                
                decision_details = f"Merged table from page {table.page_number} into page {last_table.page_start} | Reasons: {', '.join(reasons)}"
                last_pt.diagnostics.merged_tables += 1
                last_pt.diagnostics.decisions.append(
                    TableProcessingDecision(
                        action=TableAction.MERGE_PAGES,
                        details=decision_details,
                        confidence=MergeConfidence.HIGH
                    )
                )
                logger.info(
                    "Merged table split between page %d and %d: Root=table_%d_%s | Child=table_%d_%s | Reasons: %s | Confidence: HIGH",
                    last_table.page_start,
                    table.page_number,
                    last_table.page_number,
                    f"{last_table.bbox[0]:.1f}_{last_table.bbox[1]:.1f}",
                    table.page_number,
                    f"{table.bbox[0]:.1f}_{table.bbox[1]:.1f}",
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
    """
    Stage E2: Renders Table model into clean, styling-ready HTML.

    Design decisions:
    - Column widths are computed from blended content-length signals (max + average),
      with numeric column detection and configurable clamping.
    - <br> inside cell text is preserved (not escaped), enabling multi-line cells.
    - Section rows and total rows receive CSS classes for PDF-renderer styling.
    - Tables with many columns receive a reduced font-size to improve A4 fit;
      they are NOT truncated. No content is ever dropped.
    """

    # Column width clamping constants — easy to tune without touching algorithm logic.
    MIN_COLUMN_WIDTH: int = 8   # % — prevents zero-width columns (e.g. "Sr." index)
    MAX_COLUMN_WIDTH: int = 55  # % — prevents one long description consuming the table

    # Wide-table thresholds
    WIDE_TABLE_THRESHOLD: int = 7   # columns ≥ this get reduced font-size
    WIDE_TABLE_FONT_SIZE: str = "8.5pt"  # reduced from the PDF body default (12pt)

    # Numeric column detection: fraction of non-empty cells that must look numeric
    NUMERIC_THRESHOLD: float = 0.70

    # Blending coefficients: weight = α·max_len + β·avg_len
    # Prevents a single outlier cell from dominating the column width.
    _ALPHA: float = 0.7  # max_length contribution
    _BETA: float = 0.3   # average_length contribution

    @staticmethod
    def _escape_cell(text: str) -> str:
        """
        Escape cell text for HTML while preserving embedded <br> line breaks
        and stripping residual inline markdown bold/italic markers.

        Stored cell text may contain residual ** markers when:
        - The original markdown had **segment1**<br>**segment2** in a single cell
        - parse_markdown_to_table() set CellStyle.BOLD on the cell but left the
          inner ** stripped only from the outermost layer.

        We strip remaining **..** and *.* here (bold/italic is handled by Cell.style
        at the wrapping level in render()), then escape and rejoin with <br />.
        """
        parts = re.split(r'<br\s*/?>', text, flags=re.IGNORECASE)
        escaped_parts = []
        for part in parts:
            # Strip residual inline ** and * markers
            part = re.sub(r'\*\*(.*?)\*\*', r'\1', part)
            part = re.sub(r'\*(.*?)\*', r'\1', part)
            escaped_parts.append(html.escape(part))
        return '<br />'.join(escaped_parts)

    @staticmethod
    def _strip_tags(text: str) -> str:
        """Remove all HTML tags to measure visible character length."""
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def _is_numeric_cell(text: str) -> bool:
        """Return True if the cell value looks like a number, currency, or blank."""
        cleaned = _HTMLRenderer._strip_tags(text).strip()
        if not cleaned:
            return True  # blank cells don't penalise numeric detection
        return bool(re.match(
            r'^[₹\-\u2013\d,\s\(\)%\.Nil]+$',
            cleaned
        ))

    @classmethod
    def _compute_col_widths(cls, table: 'Table') -> list:
        """
        Compute percentage widths for each column.

        Algorithm:
        1. For each column, collect visible text lengths of all cells.
        2. Raw weight = α·max_len + β·avg_len  (blended — resistant to outliers)
        3. Numeric columns: weight is halved (numbers are visually narrow).
        4. Normalize weights → initial percentages.
        5. Clamp each column to [MIN_COLUMN_WIDTH, MAX_COLUMN_WIDTH].
        6. Re-normalize so percentages sum to 100.

        Very wide tables (≥ WIDE_TABLE_THRESHOLD columns) still use this algorithm;
        the font-size reduction is applied at the render level, not here.
        """
        if not table.rows:
            return []

        num_cols = max(len(row.cells) for row in table.rows)
        if num_cols == 0:
            return []

        col_lengths: list = [[] for _ in range(num_cols)]
        col_numeric_votes: list = [[] for _ in range(num_cols)]

        for row in table.rows:
            for j, cell in enumerate(row.cells):
                if j >= num_cols:
                    break
                visible = cls._strip_tags(cell.text)
                col_lengths[j].append(len(visible))
                if not row.is_header:  # only data rows count for numeric detection
                    col_numeric_votes[j].append(cls._is_numeric_cell(cell.text))

        weights = []
        is_numeric_cols = []
        for j in range(num_cols):
            lengths = col_lengths[j]
            if not lengths:
                weights.append(float(cls.MIN_COLUMN_WIDTH))
                is_numeric_cols.append(False)
                continue

            max_len = max(lengths)
            avg_len = sum(lengths) / len(lengths)
            # Calculate raw weight dynamically based on maximum and average text lengths in the column
            raw_weight = max(
                cls._ALPHA * max_len + cls._BETA * avg_len,
                5.0  # minimum weight so zero-content columns still get a slot
            )
            weights.append(raw_weight)

        # Normalize to percentages
        total_weight = sum(weights) or 1.0
        pcts = [(w / total_weight) * 100.0 for w in weights]

        # Dynamic Proportional Column Bounds (scales proportionally with text/header lengths):
        min_pcts = [10.0 for _ in range(num_cols)]
        max_pcts = [85.0 if num_cols > 1 else 100.0 for _ in range(num_cols)]

        max_iters = max(20, len(pcts) * 3)
        for _ in range(max_iters):
            if all(min_pcts[j] - 0.01 <= pcts[j] <= max_pcts[j] + 0.01 for j in range(num_cols)):
                break
            clamped = [max(min_pcts[j], min(max_pcts[j], pcts[j])) for j in range(num_cols)]
            total_clamped = sum(clamped) or 1.0
            pcts = [(p / total_clamped) * 100.0 for p in clamped]

        return pcts

    @classmethod
    def render(cls, table: 'Table') -> str:
        is_complex = table.properties.get("is_complex", False)
        regions = table.properties.get("regions", [])
        crop_path = table.properties.get("crop_path")
        if not regions and crop_path:
            regions = [{
                "page_number": table.page_number,
                "bbox": [round(float(c), 1) for c in table.bbox] if table.bbox else None,
                "crop_path": crop_path
            }]
            
        provenance_attr = ""
        crop_attr = ""
        if regions or crop_path or is_complex:
            provenance_data = {
                "page_start": table.page_start,
                "page_end": table.page_end,
                "regions": [
                    {
                        "page_number": r.get("page_number"),
                        "bbox": r.get("bbox")
                    } for r in regions
                ]
            }
            provenance_json = html.escape(json.dumps(provenance_data))
            first_crop = (regions[0].get("crop_path") or "").replace("\\", "/") if regions else ""
            if first_crop and not first_crop.startswith('/'):
                first_crop = '/' + first_crop
            provenance_attr = f' data-table-provenance="{provenance_json}"'
            crop_attr = f' data-crop-path="{first_crop}"' if first_crop else ''

        complex_attr = ' data-is-complex="true"' if is_complex else ''
        container_attrs = f'{complex_attr}{crop_attr}{provenance_attr}'
        # ── Complex Visual Object / Source PDF Region Presentation ──
        if is_complex and regions:
            img_blocks = []
            for r in regions:
                cp = r.get("crop_path")
                if cp:
                    img_src = cp.replace("\\", "/").lstrip('/')
                    img_blocks.append(
                        f'  <div class="table-visual-region" style="text-align:center; margin: 0.5em 0;">'
                        f'<img src="/{img_src}" style="max-width: 100%; height: auto; display: block; margin: 0.5em auto;" />'
                        f'</div>'
                    )
            if img_blocks:
                return f'<div class="table-container"{container_attrs}>\n' + "\n".join(img_blocks) + '\n</div>'

        if not table.rows:
            return ""

        num_cols = max(len(row.cells) for row in table.rows) if table.rows else 0

        # --- Prune all-empty columns ---
        # Columns where every single cell (header and data) is blank are
        # spacer artifacts from PyMuPDF extraction. Remove them entirely so
        # they don't consume width or produce phantom <th></th> cells.
        keep_col_indices = []
        for col_idx in range(num_cols):
            has_content = False
            for row in table.rows:
                if col_idx < len(row.cells) and row.cells[col_idx].text.strip():
                    has_content = True
                    break
            if has_content:
                keep_col_indices.append(col_idx)

        if not keep_col_indices:
            return ""  # entirely empty table

        # Re-index the table to only the kept columns
        if len(keep_col_indices) < num_cols:
            pruned_rows = []
            for row in table.rows:
                new_cells = [row.cells[i] for i in keep_col_indices if i < len(row.cells)]
                pruned_rows.append(Row(
                    cells=new_cells,
                    is_header=row.is_header,
                    is_section=row.is_section,
                    is_total=row.is_total,
                ))
            table = Table(rows=pruned_rows, bbox=table.bbox, page_number=table.page_number)

        num_cols = len(keep_col_indices)
        is_wide = num_cols >= cls.WIDE_TABLE_THRESHOLD

        html_parts = [f'<div class="table-container"{container_attrs}>']

        # Wide-table note (informational, printed in small italic above the table)
        # The table is NOT truncated; font-size is reduced instead.
        if is_wide:
            html_parts.append(
                f'<p style="font-size:8pt;font-style:italic;margin:0 0 2px 0;">'
                f'Wide table ({num_cols} columns) — font size reduced for A4 fit.'
                f'</p>'
            )

        # Add wide-table class for tables with 5 or more columns
        num_cols = max(len(row.cells) for row in table.rows) if table.rows else 0
        table_class = "structured-table wide-table" if num_cols >= 5 else "structured-table"
        html_parts.append(f'<table class="{table_class}">')

        # Omit <colgroup> overrides to allow xhtml2pdf and web browsers to distribute column widths dynamically

        # --- <thead> ---
        has_header = any(row.is_header for row in table.rows)
        if has_header:
            html_parts.append('<thead>')
            for row in table.rows:
                if not row.is_header:
                    continue
                html_parts.append('<tr>')
                for cell in row.cells:
                    align = ''
                    if cell.alignment == CellAlignment.RIGHT:
                        align = ' style="text-align:right;"'
                    elif cell.alignment == CellAlignment.CENTER:
                        align = ' style="text-align:center;"'
                    colspan = f' colspan="{cell.colspan}"' if cell.colspan > 1 else ''
                    rowspan = f' rowspan="{cell.rowspan}"' if cell.rowspan > 1 else ''
                    inner = cls._escape_cell(cell.text)
                    if cell.style == CellStyle.BOLD:
                        inner = f'<strong>{inner}</strong>'
                    html_parts.append(f'<th{align}{colspan}{rowspan}>{inner}</th>')
                html_parts.append('</tr>')
            html_parts.append('</thead>')

        # --- <tbody> ---
        html_parts.append('<tbody>')
        for row in table.rows:
            if row.is_header:
                continue

            # CSS class — section rows and total rows get dedicated classes
            # so the PDF renderer can style them without extra inline styles.
            row_class = ''
            if row.is_section:
                row_class = ' class="section-row"'
            elif row.is_total:
                row_class = ' class="total-row"'

            html_parts.append(f'<tr{row_class}>')
            for cell in row.cells:
                align = ''
                if cell.alignment == CellAlignment.RIGHT:
                    align = ' style="text-align:right;"'
                elif cell.alignment == CellAlignment.CENTER:
                    align = ' style="text-align:center;"'
                colspan = f' colspan="{cell.colspan}"' if cell.colspan > 1 else ''
                rowspan = f' rowspan="{cell.rowspan}"' if cell.rowspan > 1 else ''

                is_bold = (
                    cell.style == CellStyle.BOLD
                    or row.is_section
                    or (row.is_total and cell.text)
                )
                inner = cls._escape_cell(cell.text)
                if is_bold:
                    inner = f'<strong>{inner}</strong>'
                html_parts.append(f'<td{align}{colspan}{rowspan}>{inner}</td>')
            html_parts.append('</tr>')
        html_parts.append('</tbody>')

        html_parts.append('</table>')
        html_parts.append('</div>')
        return ''.join(html_parts)





MCQ_OPTION_PATTERN = re.compile(
    r'(?i)(?:'
    r'\bOption\b\s*[:\-]?(?:\s*\(?[a-eA-E]\)?)?'
    r'|'
    r'\bAns(?:wer)?\.?\s*[:\-]?(?:\s*\(?[a-eA-E]\)?)?'
    r'|'
    r'\([a-eA-E]\)'
    r'|'
    r'^\s*\(?[a-eA-E]\)[\.\:\-]?'
    r')'
)

MCQ_COMBINED_PATTERN = re.compile(
    r'^\s*(?:Q\.?\s*(?:No\.?)?\s*|MCQ\s*(?:No\.?)?\s*)?(?:[1-9]\d?\s*[\.\)]\s*)?'
    r'(?:[IVXLCDM]+|[1-9]\d?|\([a-z]\)|\([0-9]+\))\s*[\.\)]?\s+'
    r'(?:'
    r'\bOption\b(?:\s*[:\-]|\s*\(?[a-eA-E]\)?)'
    r'|'
    r'\bAns(?:wer)?\.?\s*[:\-]?(?:\s*\(?[a-eA-E]\)?)'
    r'|'
    r'\([a-eA-E]\)'
    r')',
    re.IGNORECASE
)

MCQ_QNUM_CELL_PATTERN = re.compile(
    r'^\s*(?:Q\.?\s*(?:No\.?)?\s*|MCQ\s*(?:No\.?)?\s*)?(?:[1-9]\d?\s*[\.\)]\s*)?'
    r'(?:[IVXLCDM]+|[1-9]\d?|\([a-z]\)|\([0-9]+\))\s*[\.\)]?\s*$',
    re.IGNORECASE
)

def is_mcq_answer_key_table(raw_grid: List[List[Any]]) -> bool:
    """
    Identifies true MCQ answer key mapping tables (e.g. Q. No | Most Appropriate Answer / Option (a) ...).
    Financial statement tables or itemized computation adjustments are never MCQ answer keys.
    """
    if not raw_grid or len(raw_grid) < 2:
        return False
        
    full_text = ' '.join(str(c or '') for row in raw_grid for c in row)
    header_text = ' '.join(str(c or '') for c in raw_grid[:3] for c in (c if isinstance(c, list) else [c]))
    
    # 1. Primary check: Explicit MCQ table header (e.g. Question No. | Answer / Most Appropriate Answer / Option)
    has_mcq_header = bool(re.search(
        r'(?i)\b(?:MCQ\s*No\.?|Most\s+Appropriate\s+Answer|Answer\s+Key|Answers?\s+to\s+Multiple\s+Choice\s+Questions?|Question\s*(?:No\.?)?[\s\S]*?(?:Answer|Option))\b',
        header_text
    ))
    has_opt = any(MCQ_OPTION_PATTERN.search(str(c)) for row in raw_grid for c in row if c)
    if has_mcq_header and has_opt:
        return True
        
    # If table contains balance sheet or journal debit/credit statement keywords, it's NOT an answer key
    if re.search(r'(?i)\b(?:Statement\s+of\s+profit|Debit\s+and\s+Credit|Balance\s+Sheet|Particulars\s+.*\s+(?:Debit|Credit|Amount))\b', full_text):
        return False

    mcq_pairs = 0
    q_num_rows = 0
    for row in raw_grid:
        non_empty = [str(c).strip() for c in row if c and str(c).strip()]
        if not non_empty:
            continue
        
        # Combined question + option in a single cell
        if any(MCQ_COMBINED_PATTERN.search(cell) for cell in non_empty):
            q_num_rows += 1
            mcq_pairs += 1
            continue

        # Separate question number cell + option cell
        q_idx = -1
        for idx, cell in enumerate(non_empty):
            if MCQ_QNUM_CELL_PATTERN.match(cell):
                q_idx = idx
                break
        
        if q_idx != -1:
            q_num_rows += 1
            row_has_opt = False
            for cell in non_empty[q_idx + 1:]:
                if MCQ_OPTION_PATTERN.search(cell):
                    row_has_opt = True
                    break
            if row_has_opt:
                mcq_pairs += 1

    min_pairs_required = 1 if has_mcq_header else 2
    return q_num_rows > 0 and mcq_pairs >= min_pairs_required and (mcq_pairs >= q_num_rows * 0.4)


def serialize_mcq_key_to_text(raw_grid: List[List[Any]]) -> str:
    """
    Converts an MCQ answer key table (e.g. [['Question No.', 'Answer'], ['1. I', '(b)'], ...])
    into structured text lines that AnswerParser / QuestionParser can parse cleanly.
    """
    lines = []
    for row in raw_grid:
        non_empty = [str(c).strip() for c in row if c and str(c).strip()]
        if not non_empty:
            continue
        if any(re.search(r'(?i)\b(?:Question\s*No\.?|MCQ|Most\s+Appropriate|Answer)\b', c) for c in non_empty):
            continue
        dedup = []
        for tok in non_empty:
            sub_toks = tok.split()
            sub_dedup = []
            for st in sub_toks:
                if not sub_dedup or st != sub_dedup[-1]:
                    sub_dedup.append(st)
            cleaned_tok = ' '.join(sub_dedup)
            if not dedup or cleaned_tok != dedup[-1]:
                dedup.append(cleaned_tok)
        line = ' '.join(dedup)
        m = re.match(r'^\s*(?:Q\.?\s*(?:No\.?)?\s*|MCQ\s*(?:No\.?)?\s*)?([1-9]\d?)[.)]?[ \t]+(\([a-zA-Z]\).*)', line)
        if m:
            lines.append(f"\n{m.group(1)}.")
            lines.append(m.group(2))
        else:
            lines.append(line)
    return '\n'.join(lines)


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

    def process_document(self, doc: Any, document_id: Any = None) -> Dict[Tuple[int, float, float], str]:
        """
        Processes all tables in a document: extracts, cleans, structurally normalizes,
        merges consecutive tables across pages, and builds the mapping of table coordinates
        to their processed Markdown text representation.
        Generates high-resolution 200 DPI PNG visual crops for complex / multi-column tables.
        """
        raw_processed_tables = []
        for page in doc:
            page_num = page.number + 1
            rect = getattr(page, 'rect', None)
            page_w = 595.0
            page_h = 842.0
            page_x0 = 0.0
            if rect and hasattr(rect, 'width'):
                try:
                    page_w = float(rect.width)
                    page_h = float(rect.height)
                    page_x0 = float(rect.x0)
                except (TypeError, ValueError):
                    page_w = 595.0
                    page_h = 842.0
                    page_x0 = 0.0

            found_tables = page.find_tables().tables if hasattr(page, 'find_tables') else []
            valid_tables = [t for t in found_tables if not is_narrative_text_box(t.extract())]
            
            # Sort tables by vertical position y0
            valid_tables.sort(key=lambda t: t.bbox[1] if t.bbox else 0)
            
            # --- SAME-PAGE DIAGRAM / TABLE REGION GROUPING ---
            # Group nearby visual tables on the same page (gap <= 60pt) so diagrams with multiple boxes
            # (such as flowcharts or multi-part structures) are captured together in a single full-width visual crop.
            # Never group tables across question/answer boundaries or major section headers.
            groups = []
            for t in valid_tables:
                if not groups:
                    groups.append([t])
                else:
                    last_group = groups[-1]
                    last_t_y1 = max(float(x.bbox[3]) for x in last_group)
                    cur_t_y0 = float(t.bbox[1])
                    
                    has_header_in_gap = False
                    if hasattr(page, 'get_text'):
                        gap_text = []
                        for b in page.get_text('blocks'):
                            if len(b) >= 7 and b[6] == 0:  # text block
                                if (last_t_y1 - 5.0 <= b[1] <= cur_t_y0 + 5.0) or (last_t_y1 - 5.0 <= b[3] <= cur_t_y0 + 5.0):
                                    gap_text.append(b[4])
                        gap_str = " ".join(gap_text).strip()
                        if (re.search(r'(?i)\b(?:Question|Answer|Ans|Sol|Solution)\s*\d+', gap_str) or 
                            re.search(r'(?i)(?:^|\n)\s*\d+\.?(?:\s*\([ivxa-dIVXA-D0-9]+\))?\s+[A-Za-z]', gap_str) or 
                            re.search(r'(?i)(?:^|\n)\s*\([ivxa-dIVXA-D0-9]+\)', gap_str) or
                            re.search(r'(?i)\bInd\s+AS\b|\bWorking\s+Notes?\b|\bCalculation\b|\bAlternatively\b', gap_str)):
                            has_header_in_gap = True

                    if cur_t_y0 <= last_t_y1 + 60.0 and not has_header_in_gap:
                        last_group.append(t)
                    else:
                        groups.append([t])

            for grp in groups:
                leader_t = grp[0]
                group_x0 = min(float(t.bbox[0]) for t in grp)
                group_x1 = max(float(t.bbox[2]) for t in grp)
                group_y0 = min(float(t.bbox[1]) for t in grp)
                group_y1 = max(float(t.bbox[3]) for t in grp)
                
                # Expand slightly to capture borders/padding without overflowing into neighboring margin headers
                crop_x0 = max(page_x0, group_x0 - 8.0)
                crop_x1 = min(page_w, group_x1 + 8.0)
                crop_y0 = max(0.0, group_y0 - 2.0)
                crop_y1 = min(page_h, group_y1 + 2.0)
                crop_rect = (crop_x0, crop_y0, crop_x1, crop_y1)
                
                # Process leader table
                raw_grid = leader_t.extract()
                pt_leader = self.process(raw_grid, bbox=leader_t.bbox, page_number=page_num)
                is_mcq_table = is_mcq_answer_key_table(raw_grid)
                is_complex = not is_mcq_table
                
                crop_path_rel = None
                if is_complex and hasattr(page, 'get_pixmap'):
                    try:
                        import pymupdf as fitz
                        import os
                        mat = fitz.Matrix(200/72, 200/72)
                        rect_fitz = fitz.Rect(crop_rect)
                        pix = page.get_pixmap(matrix=mat, clip=rect_fitz)
                        try:
                            from django.conf import settings
                            media_root = getattr(settings, "MEDIA_ROOT", None)
                            if not media_root:
                                media_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "media"))
                        except Exception:
                            media_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "media"))
                        crop_dir = os.path.join(str(media_root), "table_crops")
                        os.makedirs(crop_dir, exist_ok=True)
                        doc_str = f"doc{document_id}" if document_id else "doc_extracted"
                        crop_filename = f"{doc_str}_p{page_num}_y{int(leader_t.bbox[1])}.png"
                        crop_path_abs = os.path.abspath(os.path.join(crop_dir, crop_filename))
                        pix.save(crop_path_abs)
                        # Store relative media path (/media/table_crops/...) for browser security compatibility
                        crop_path_rel = f"/media/table_crops/{crop_filename}"
                    except Exception as e:
                        logger.warning("Failed to generate PNG table crop: %s", e)

                region_info = {
                    "page_number": page_num,
                    "bbox": [round(float(c), 1) for c in crop_rect],
                    "crop_path": crop_path_rel
                }
                
                pt_leader.table.properties["regions"] = [region_info]
                pt_leader.table.properties["is_complex"] = is_complex
                if crop_path_rel:
                    pt_leader.table.properties["crop_path"] = crop_path_rel

                raw_processed_tables.append(pt_leader)
                
                # Mark child tables as merged into leader so they don't produce duplicate image crops
                for child_t in grp[1:]:
                    raw_grid_c = child_t.extract()
                    pt_child = self.process(raw_grid_c, bbox=child_t.bbox, page_number=page_num)
                    pt_child.table.properties["merged_into"] = id(leader_t)
                    pt_child.table.properties["regions"] = []
                    raw_processed_tables.append(pt_child)
                
        # Merge cross-page tables
        self.merge_cross_page_tables(raw_processed_tables, doc)
        
        # Build lookup map: (page_number, round(x0, 1), round(y0, 1)) -> markdown
        table_lookup = {}
        for pt in raw_processed_tables:
            table = pt.table
            key = (table.page_number, round(table.bbox[0], 1), round(table.bbox[1], 1))
            
            # MCQ answer key tables should always serialize to text on their respective pages
            if is_mcq_answer_key_table(table.original_grid):
                table_lookup[key] = serialize_mcq_key_to_text(table.original_grid)
                continue
                
            parent_id = table.properties.get("merged_into")
            if parent_id is not None:
                # Child chunk: render nothing on this page (merged into root)
                table_lookup[key] = ""
            else:
                # Root table:
                md = self.render_to_html(table)
                table_lookup[key] = md
                
        return table_lookup

    @staticmethod
    def serialize_to_markdown(table: Table) -> str:
        """Stage E1: Serializes Table model to Markdown representation."""
        return _MarkdownSerializer.serialize(table)

    @staticmethod
    def render_to_html(table: Table) -> str:
        """Stage E2: Renders Table model to HTML representation."""
        return _HTMLRenderer.render(table)


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
                # --- Pre-clean: unescape HTML entities from stored markdown ---
                # Stored markdown may have &lt;br&gt; from earlier HTML-escaping.
                cell_text = cell_text.replace('&lt;br&gt;', '<br>').replace('&lt;br/&gt;', '<br>').replace('&lt;br /&gt;', '<br>')
                cell_text = cell_text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

                # --- Replace backtick with rupee symbol ---
                # ICAI PDFs use backtick ` as a proxy for the ₹ rupee symbol
                # (OCR artifact). Replace standalone ` with ₹.
                cell_text = re.sub(r'`\s*(\d)', r'₹ \1', cell_text)  # ` 1,234 → ₹ 1,234
                cell_text = re.sub(r'`', '₹', cell_text)            # remaining lone ` → ₹

                style = CellStyle.NORMAL
                clean_text = cell_text
                
                if cell_text.startswith('**') and cell_text.endswith('**') and len(cell_text) > 4:
                    style = CellStyle.BOLD
                    clean_text = cell_text[2:-2].strip()
                elif cell_text.startswith('*') and cell_text.endswith('*') and len(cell_text) > 2:
                    style = CellStyle.ITALIC
                    clean_text = cell_text[1:-1].strip()

                # --- Filter dummy PyMuPDF column names ---
                # PyMuPDF names unreadable columns Col1, Col2 … Col99.
                # These are display artifacts — replace with empty string.
                if re.match(r'^Col\d+$', clean_text.strip(), re.IGNORECASE):
                    clean_text = ''
                    
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
