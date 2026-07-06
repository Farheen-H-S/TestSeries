import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum

class LayoutType(Enum):
    SECTION_WISE = "SECTION_WISE"
    INTERLEAVED = "INTERLEAVED"
    UNKNOWN = "UNKNOWN"

class QuestionLevel(Enum):
    MAIN = "MAIN"
    SUB = "SUB"
    SUB_SUB = "SUB_SUB"

@dataclass
class LayoutResult:
    layout: LayoutType
    boundary_position: Optional[int] = None
    reason: str = ""

@dataclass
class ParsedQuestion:
    hierarchy_path: List[str]
    raw_header: str
    text: str
    start_offset: int  # Absolute offset in original document
    end_offset: int    # Absolute offset in original document
    start_page: int
    end_page: int
    level: QuestionLevel = QuestionLevel.MAIN

@dataclass
class ParsedAnswer:
    hierarchy_path: List[str]
    raw_header: str
    text: str
    start_offset: int  # Absolute offset in original document
    end_offset: int    # Absolute offset in original document
    start_page: int
    end_page: int

@dataclass
class ParsingDiagnostics:
    total_matches: int = 0
    validated_count: int = 0
    rejected_headers: List[Dict[str, str]] = field(default_factory=list) # {"header": str, "reason": str}

@dataclass
class MatchingDiagnostics:
    matched_count: int = 0
    unmatched_questions: List[str] = field(default_factory=list)
    unmatched_answers: List[str] = field(default_factory=list)
    duplicate_question_ids: List[str] = field(default_factory=list)
    duplicate_answer_ids: List[str] = field(default_factory=list)
    ambiguous_matches: List[str] = field(default_factory=list)
    rejected_headers: List[Dict[str, str]] = field(default_factory=list)
    processing_time_ms: float = 0.0

@dataclass
class MatchingResult:
    matches: List[Tuple[ParsedQuestion, ParsedAnswer]]
    diagnostics: MatchingDiagnostics

@dataclass
class ParserConfig:
    # Compiled delimiters for SECTION_WISE layout
    section_delimiters: List[re.Pattern]
    # Compiled header patterns for Questions and Answers
    question_header_patterns: List[re.Pattern]
    answer_header_patterns: List[re.Pattern]
    # Specific keywords for classification
    case_study_keywords: List[str]
    instruction_priority: List[str]
    # Compiled marks patterns
    marks_patterns: List[re.Pattern]
    marks_exclusion_patterns: List[re.Pattern]
