import re
import logging
from typing import List, Tuple, Optional
from .types import ParsedAnswer, ParserConfig, AnswerParseResult, ParsingDiagnostics, ParsingContext, AnswerSectionType

from .normalizer import Normalizer
from .hierarchy_utils import HierarchyUtils
from .header_validator import HeaderValidator

logger = logging.getLogger(__name__)


class AnswerParser:
    """
    Greedy parser for extracting answer blocks.
    Deduplicates matches and uses binary search for performance.
    """
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.normalizer = Normalizer()
        self.validator = HeaderValidator()
        self.diagnostics = ParsingDiagnostics()

    def parse(self, text: str, page_offsets: List[Tuple[int, int]], base_offset: int = 0, context: Optional[ParsingContext] = None) -> List[ParsedAnswer]:
        """
        Parses text into a list of answers with stateful path resolution and absolute offsets.
        """
        result = self.parse_with_diagnostics(text, page_offsets, base_offset, context)
        self.diagnostics = result.diagnostics
        return result.answers



    def parse_with_diagnostics(
        self,
        text: str,
        page_offsets: List[Tuple[int, int]],
        base_offset: int = 0,
        context: Optional[ParsingContext] = None,
    ) -> AnswerParseResult:
        """
        Parses text and returns an AnswerParseResult that bundles the
        answers list with the diagnostics from this run.
        """
        # Pre-normalize the text for OCR errors before matching
        normalized_text = self.normalizer.pre_normalize_ocr(text)

        # Collect all potential matches from all patterns using the normalized text
        raw_matches = []
        for p_idx, regex in enumerate(self.config.answer_header_patterns):
            for match in regex.finditer(normalized_text):
                raw_matches.append((match, p_idx))
            
        # Resolve overlapping matches: Sort by start index ascending, length descending, and pattern priority ascending
        raw_matches.sort(key=lambda x: (x[0].start(), -x[0].end(), x[1]))
        resolved_matches: List[Tuple[re.Match, int]] = []

        for match, p_idx in raw_matches:
            is_accepted = True
            to_remove = []

            for j, (other_match, other_p_idx) in enumerate(resolved_matches):
                if match.start() < other_match.end() and other_match.start() < match.end():
                    # Overlapping: compare by length then pattern priority
                    match_len = match.end() - match.start()
                    other_len = other_match.end() - other_match.start()
                    if match_len > other_len or (match_len == other_len and p_idx < other_p_idx):
                        to_remove.append(j)
                    else:
                        is_accepted = False
                        break

            if is_accepted:
                for idx in sorted(to_remove, reverse=True):
                    resolved_matches.pop(idx)
                resolved_matches.append((match, p_idx))

        all_potential_matches = sorted([m for m, _ in resolved_matches], key=lambda x: x.start())
        diagnostics = ParsingDiagnostics(total_matches=len(all_potential_matches))

        if not all_potential_matches:
            return AnswerParseResult(answers=[], diagnostics=diagnostics)

        # Precompute page keys for true O(log n) lookup
        page_keys = [x[0] for x in page_offsets] if page_offsets else []

        parsed_answers = []
        hierarchy_stack: List[str] = []
        validated_matches = []
        
        # Classify sections
        sections = self._classify_sections(normalized_text)

        logger.info(
            "Answer parsing stage 1 | potential_matches=%d",
            len(all_potential_matches)
        )

        for match in all_potential_matches:
            # Skip matches that fall inside a local Working Notes zone; they belong to the parent answer's working notes
            if self._is_inside_working_notes_zone(match.start(), normalized_text):
                raw_header = text[match.start():match.end()]
                logger.info("Answer candidate rejected | candidate=%r | reason=inside Working Notes zone | start_offset=%d", raw_header, match.start())
                diagnostics.rejected_headers.append({
                    "header": raw_header,
                    "reason": "inside Working Notes zone"
                })
                continue

            # Check if this match falls inside a structured block (table region)
            if self._is_inside_structured_block(match.start(), normalized_text):
                if context:
                    context.inside_structured_block = True
                raw_header = text[match.start():match.end()]
                logger.info("Answer candidate rejected | candidate=%r | reason=inside structured block | start_offset=%d", raw_header, match.start())
                diagnostics.rejected_headers.append({
                    "header": raw_header,
                    "reason": "inside structured block"
                })
                continue
            else:
                if context:
                    context.inside_structured_block = False
                    
            normalized_header = match.group(0)
            path = self.normalizer.normalize_header(normalized_header)
            
            result = self.validator.is_valid(match, path, hierarchy_stack, normalized_text)
            if result.is_valid:
                old_stack = list(hierarchy_stack)
                HierarchyUtils.update_hierarchy_stack(hierarchy_stack, path)
                logger.debug(
                    "Hierarchy stack transition (Answer) | old_stack=%s | new_stack=%s | header=%s | start_offset=%d",
                    old_stack, hierarchy_stack, normalized_header, match.start()
                )
                validated_matches.append((match, list(hierarchy_stack)))
            else:
                raw_header = text[match.start():match.end()]
                reason_str = result.reason or "Unknown rejection"
                logger.info(
                    "Answer candidate rejected | candidate=%r | reason=%s | start_offset=%d",
                    raw_header, reason_str, match.start()
                )
                diagnostics.rejected_headers.append({
                    "header": raw_header,
                    "reason": reason_str
                })

        logger.info(
            "Answer parsing stage 2 | potential=%d | validated=%d | rejected=%d",
            len(all_potential_matches), len(validated_matches), len(diagnostics.rejected_headers)
        )

        for i, (match, h_path) in enumerate(validated_matches):
            raw_header = text[match.start():match.end()]
            start_offset = base_offset + match.start()
            
            next_match_start = validated_matches[i+1][0].start() if i + 1 < len(validated_matches) else len(text)
            end_offset = base_offset + next_match_start
            
            block_text = text[match.end():next_match_start].strip()
            
            # Determine section type based on match offset
            sec_type = self._get_section_type(match.start(), sections)
            
            # Extract working notes inside this answer block if present
            main_text, working_notes = self._extract_working_notes(block_text, base_offset + match.end())

            # Use centralized O(log n) page lookup from HierarchyUtils
            start_page = HierarchyUtils.get_page_num_fast(start_offset, page_offsets, page_keys)
            end_page = HierarchyUtils.get_page_num_fast(end_offset - 1, page_offsets, page_keys)
            
            parsed_answers.append(ParsedAnswer(
                hierarchy_path=h_path,
                raw_header=raw_header,
                text=main_text,
                start_offset=start_offset,
                end_offset=end_offset,
                start_page=start_page,
                end_page=end_page,
                section_type=sec_type,
                working_notes=working_notes
            ))
            
        diagnostics.validated_count = len(parsed_answers)
        logger.info(
            "Answer parsing stage 3 | returning_parsed_answers=%d",
            len(parsed_answers)
        )
        return AnswerParseResult(answers=parsed_answers, diagnostics=diagnostics)


    def _classify_sections(self, text: str) -> List[Tuple[int, AnswerSectionType]]:
        from .extraction_patterns import MCQ_ANSWER_SECTION_PATTERNS, WORKING_NOTE_SECTION_PATTERNS, MAIN_ANSWER_SECTION_PATTERNS
        from .types import AnswerSectionType

        section_matches = []

        for pat in MCQ_ANSWER_SECTION_PATTERNS:
            for m in re.finditer(pat, text, re.MULTILINE):
                section_matches.append((m.start(), AnswerSectionType.MCQ_ANSWER))

        for pat in WORKING_NOTE_SECTION_PATTERNS:
            for m in re.finditer(pat, text, re.MULTILINE):
                section_matches.append((m.start(), AnswerSectionType.WORKING_NOTE))

        for pat in MAIN_ANSWER_SECTION_PATTERNS:
            for m in re.finditer(pat, text, re.MULTILINE):
                section_matches.append((m.start(), AnswerSectionType.MAIN_ANSWER))

        section_matches.sort(key=lambda x: x[0])
        return section_matches

    def _get_section_type(self, offset: int, sections: List[Tuple[int, AnswerSectionType]]) -> AnswerSectionType:
        from .types import AnswerSectionType
        current_type = AnswerSectionType.MAIN_ANSWER
        for sec_start, sec_type in sections:
            if sec_start <= offset:
                current_type = sec_type
            else:
                break
        return current_type

    def _extract_working_notes(self, block_text: str, base_offset: int) -> Tuple[str, List[WorkingNote]]:
        from .types import WorkingNote
        
        wn_marker = re.search(r"(?im)^[ \t]*(?:Working\s+Notes?|W\.?N\.?)\s*[:\-–—]?", block_text)
        if not wn_marker:
            return block_text, []

        main_text = block_text[:wn_marker.start()].strip()
        wn_block = block_text[wn_marker.end():].strip()

        wn_item_regex = re.compile(
            r"(?im)^[ \t]*(?:Working\s+Note|W\.?N\.?|Note)?\s*(\d+)[.)]?\s*(.*?)$"
        )
        matches = list(wn_item_regex.finditer(wn_block))
        if not matches:
            # Fallback single working note if no numbered items found
            return main_text, [WorkingNote(number="1", title=None, content=wn_block)]

        working_notes = []
        for idx, m in enumerate(matches):
            num = m.group(1)
            raw_title = m.group(2).strip() if m.group(2) else None
            
            start_pos = m.end()
            end_pos = matches[idx+1].start() if idx + 1 < len(matches) else len(wn_block)
            content = wn_block[start_pos:end_pos].strip()

            title = raw_title if raw_title and len(raw_title) < 120 else None
            working_notes.append(WorkingNote(
                number=num,
                title=title,
                content=content,
                start_offset=base_offset + wn_marker.end() + m.start(),
                end_offset=base_offset + wn_marker.end() + end_pos
            ))

        return main_text, working_notes


    def _is_inside_working_notes_zone(self, start_idx: int, normalized_text: str) -> bool:
        """
        Checks if a candidate match falls inside a local Working Notes zone
        (preceded by 'Working Notes:' without an intervening top-level answer header).
        """
        wn_matches = list(re.finditer(r"(?im)^[ \t]*(?:Working\s+Notes?|W\.?N\.?)\s*[:\-–—]?", normalized_text[:start_idx]))
        if not wn_matches:
            return False

        last_wn = wn_matches[-1]
        wn_pos = last_wn.start()
        gap_segment = normalized_text[wn_pos:start_idx]

        # Working notes zone is terminated by a top-level question/answer header or section header
        top_level_pattern = re.compile(
            r"(?im)^[ \t]*(?:Answer\s+(?:to\s+)?(?:Question\s+)?|Ans\.?\s*|Solution\s*|Question\s+|Q\.?\s*)(?:No\.\s*)?\d+"
            r"|^[ \t]*(?:Suggested\s+Answers?|Suggested\s+Solutions?|Part\s+[I|V|X]+|Answers?\s+to\s+Questions?)"
        )
        if top_level_pattern.search(gap_segment):
            return False

        return True



    def _is_inside_structured_block(self, start_idx: int, text: str) -> bool:
        last_start = text.rfind("[STRUCTURED_START]", 0, start_idx)
        if last_start == -1:
            return False
        last_end = text.rfind("[STRUCTURED_END]", 0, start_idx)
        return last_start > last_end



