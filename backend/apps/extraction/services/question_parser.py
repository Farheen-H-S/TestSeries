import re
import bisect
import logging
from typing import List, Optional, Dict, Any, Tuple
from .types import ParsedQuestion, QuestionLevel, ParserConfig, ParsingDiagnostics, QuestionParseResult
from .normalizer import Normalizer
from .header_validator import HeaderValidator
from .hierarchy_utils import HierarchyUtils

logger = logging.getLogger(__name__)


class QuestionParser:
    """
    Greedy, hierarchy-aware parser for extracting question blocks.
    Delegates validation to HeaderValidator and uses binary search for performance.
    """
    SEMANTIC_SCORE_THRESHOLD = 2
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.normalizer = Normalizer()
        self.validator = HeaderValidator()
        self.diagnostics = ParsingDiagnostics()

    def parse(
        self,
        text: str,
        page_offsets: List[Tuple[int, int]],
        base_offset: int = 0,
        enable_semantic_validation: bool = False
    ) -> List[ParsedQuestion]:
        """
        Parses text into a list of hierarchical questions with strict validation and offset correction.
        """
        result = self.parse_with_diagnostics(text, page_offsets, base_offset, enable_semantic_validation)
        self.diagnostics = result.diagnostics
        return result.questions



    def parse_with_diagnostics(
        self,
        text: str,
        page_offsets: List[Tuple[int, int]],
        base_offset: int = 0,
        enable_semantic_validation: bool = False,
    ) -> QuestionParseResult:
        """
        Parses text and returns a QuestionParseResult that bundles the
        questions list with the diagnostics from this run.
        """
        # Pre-normalize the text for OCR errors before matching
        normalized_text = self.normalizer.pre_normalize_ocr(text)

        # Collect all potential matches from all patterns using the normalized text
        raw_matches = []
        for p_idx, regex in enumerate(self.config.question_header_patterns):
            for match in regex.finditer(normalized_text):
                raw_matches.append((match, p_idx))
        
        # Resolve overlapping matches: Sort by start index ascending, length descending, and pattern priority ascending
        raw_matches.sort(key=lambda x: (x[0].start(), -x[0].end(), x[1]))
        resolved_matches: List[Tuple[re.Match, int]] = []
        
        for match, p_idx in raw_matches:
            is_valid_overlap = True
            matches_to_remove = []
            
            for j, (other_match, other_p_idx) in enumerate(resolved_matches):
                # Check for overlap
                if match.start() < other_match.end() and other_match.start() < match.end():
                    # Priority: 1. Longer match | 2. Higher pattern priority (lower p_idx)
                    match_len = match.end() - match.start()
                    other_len = other_match.end() - other_match.start()
                    
                    if match_len > other_len:
                        matches_to_remove.append(j)
                    elif match_len == other_len and p_idx < other_p_idx:
                        matches_to_remove.append(j)
                    else:
                        is_valid_overlap = False
                        break
            
            if is_valid_overlap:
                # Remove overlapping matches that this new match beats
                for idx in sorted(matches_to_remove, reverse=True):
                    resolved_matches.pop(idx)
                resolved_matches.append((match, p_idx))
        
        all_potential_matches = sorted([m for m, _ in resolved_matches], key=lambda x: x.start())
        diagnostics = ParsingDiagnostics(total_matches=len(all_potential_matches))
        
        if not all_potential_matches:
            return QuestionParseResult(questions=[], diagnostics=diagnostics)

        # Precompute page keys for true O(log n) lookup
        page_keys = [x[0] for x in page_offsets] if page_offsets else []

        parsed_questions = []
        hierarchy_stack: List[str] = []
        
        validated_matches = []
        for i, match in enumerate(all_potential_matches):
            normalized_header = match.group(0)
            path = self.normalizer.normalize_header(normalized_header)
            
            # Decompose path to check levels
            main_num, alpha, roman = HierarchyUtils.decompose_path(path)
            level = self._get_level(path)
            
            # Extract block text for semantic validation (from match.end() to next match.start() or end of text)
            next_match_start = all_potential_matches[i+1].start() if i + 1 < len(all_potential_matches) else len(normalized_text)
            block_text = normalized_text[match.end():next_match_start].strip()
            
            # 1. Semantic Check (Only if enabled)
            if enable_semantic_validation:
                has_active_main = hierarchy_stack and hierarchy_stack[0].isdigit()
                is_digit_main = path and path[0].isdigit()
                
                # Semantic checks apply to digit-based main questions or any candidate starting a root hierarchy
                if is_digit_main or not has_active_main:
                    if is_digit_main:
                        # Look ahead to the next main question candidate to evaluate semantic score across the entire question block (including sub-questions)
                        next_main_start = len(normalized_text)
                        for next_match in all_potential_matches[i+1:]:
                            next_path = self.normalizer.normalize_header(next_match.group(0))
                            if next_path and next_path[0].isdigit():
                                next_main_start = next_match.start()
                                break
                        semantic_block_text = normalized_text[match.end():next_main_start].strip()
                    else:
                        # For sub-questions starting a mainless structure, use only their own direct text block
                        semantic_block_text = block_text
                    
                    score, score_reasons = self._score_semantics(semantic_block_text)
                    if score < self.SEMANTIC_SCORE_THRESHOLD:
                        logger.debug("Rejecting non-semantic root question candidate: %s | score=%d | reasons=%s", normalized_header, score, score_reasons)
                        diagnostics.rejected_headers.append({
                            "header": text[match.start():match.end()],
                            "reason": f"non-semantic question block (score: {score}, triggered: {score_reasons})"
                        })
                        continue
            
            # 2. Structural/Hierarchy Validation
            result = self.validator.is_valid(match, path, hierarchy_stack, normalized_text)
            if result.is_valid:
                old_stack = list(hierarchy_stack)
                # Update stack to get the full hierarchical path for this question
                HierarchyUtils.update_hierarchy_stack(hierarchy_stack, path)
                logger.debug(
                    "Hierarchy stack transition | old_stack=%s | new_stack=%s | header=%s | start_offset=%d",
                    old_stack, hierarchy_stack, normalized_header, match.start()
                )
                # Capture current stack state as the path for this question
                validated_matches.append((match, list(hierarchy_stack)))
            else:
                # Use the original header from original text for diagnostics
                raw_header = text[match.start():match.end()]
                logger.debug(
                    "Rejected question header candidate | candidate=%s | reason=%s | start_offset=%d",
                    raw_header, result.reason or "Unknown rejection", match.start()
                )
                diagnostics.rejected_headers.append({
                    "header": raw_header, 
                    "reason": result.reason or "Unknown rejection"
                })
 
        diagnostics.validated_count = len(validated_matches)
        if not validated_matches:
            return QuestionParseResult(questions=[], diagnostics=diagnostics)
 
        for i, (match, h_path) in enumerate(validated_matches):
            # Extract raw header from original text to preserve OCR typo exact matches
            raw_header = text[match.start():match.end()]
            start_offset = base_offset + match.start()
            
            next_match_start = validated_matches[i+1][0].start() if i + 1 < len(validated_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            # Extract actual text from original document
            block_text = text[match.end():next_match_start].strip()
            
            level = self._get_level(h_path)
            
            # Use centralized O(log n) page lookup from HierarchyUtils
            start_page = HierarchyUtils.get_page_num_fast(start_offset, page_offsets, page_keys)
            end_page = HierarchyUtils.get_page_num_fast(end_offset - 1, page_offsets, page_keys)
            
            parsed_questions.append(ParsedQuestion(
                hierarchy_path=h_path,
                raw_header=raw_header,
                text=block_text,
                start_offset=start_offset,
                end_offset=end_offset,
                start_page=start_page,
                end_page=end_page,
                level=level
            ))
            
        return QuestionParseResult(questions=parsed_questions, diagnostics=diagnostics)

    def _score_semantics(self, text: str) -> Tuple[int, List[str]]:
        score = 0
        reasons = []
        
        # Positive signals
        if "?" in text:
            score += 2
            reasons.append("has_question_mark")
            
        if re.search(r"\b\d+\s*marks?\b", text, re.IGNORECASE) or re.search(r"\(\s*\d+\s*\)", text) or re.search(r"\[\s*\d+\s*\]", text):
            score += 2
            reasons.append("has_marks_indication")
            
        if re.search(r"(?i)\b(?:Question|Q\.)\b", text):
            score += 2
            reasons.append("starts_with_question_keyword")
            
        # Case-insensitive verbs check (safe now due to negative signals balancing)
        verbs = r"(?i)\b(?:Explain|Calculate|Discuss|Determine|State|Compute|Prepare|Journalise|Find\s+out|Show|Describe|Analyse|Evaluate|Identify|Compare|Distinguish)\b"
        if re.search(verbs, text):
            score += 2
            reasons.append("has_instruction_verb")
            
        # Negative signals
        if re.search(r"(?i)\bnotification\b", text):
            score -= 3
            reasons.append("has_negative_notification")
        if re.search(r"(?i)\bamendment\b", text):
            score -= 3
            reasons.append("has_negative_amendment")
        if re.search(r"(?i)\beffective\s+from\b", text):
            score -= 2
            reasons.append("has_negative_effective_from")
        if re.search(r"(?i)\bshall\s+substitute\b", text):
            score -= 4
            reasons.append("has_negative_shall_substitute")
        if re.search(r"(?i)\blegislative\b", text):
            score -= 3
            reasons.append("has_negative_legislative")
            
        return score, reasons

    def _is_semantic_question(self, text: str) -> bool:
        score, _ = self._score_semantics(text)
        return score >= self.SEMANTIC_SCORE_THRESHOLD

    def _get_level(self, path: List[str]) -> QuestionLevel:
        if len(path) >= 3: return QuestionLevel.SUB_SUB
        if len(path) == 2: return QuestionLevel.SUB
        return QuestionLevel.MAIN
