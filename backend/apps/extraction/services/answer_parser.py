import re
import logging
from typing import List, Tuple, Optional, Dict, Set
from .types import ParsedAnswer, ParserConfig, AnswerParseResult, ParsingDiagnostics, ParsingContext, AnswerSectionType, AnswerSource, PromotionReason, PromotionEvaluation, PromotionContext, WorkingNote

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

    def parse(self, text: str, page_offsets: List[Tuple[int, int]], base_offset: int = 0, context: Optional[ParsingContext] = None, valid_question_paths: Optional[Set[Tuple[str, ...]]] = None) -> List[ParsedAnswer]:
        """
        Parses text into a list of answers with stateful path resolution and absolute offsets.
        """
        result = self.parse_with_diagnostics(text, page_offsets, base_offset, context, valid_question_paths)
        self.diagnostics = result.diagnostics
        return result.answers



    def parse_with_diagnostics(
        self,
        text: str,
        page_offsets: List[Tuple[int, int]],
        base_offset: int = 0,
        context: Optional[ParsingContext] = None,
        valid_question_paths: Optional[Set[Tuple[str, ...]]] = None,
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

        from .extraction_patterns import WORKING_NOTE_HEADER_PATTERNS, WORKING_NOTE_SECTION_PATTERNS
        from .types import ParserState

        parser_state = ParserState.DEFAULT
        working_notes_start_offset = 0
        last_working_note_offset = 0
        last_working_note_num = 0
        prev_match_end = 0

        max_wn_len = getattr(self.config, 'max_working_notes_length', 4000)

        # Precompute known_children for O(1) lookup
        known_children = {}
        if valid_question_paths is not None:
            for path in valid_question_paths:
                parent_path = path[:-1]
                if parent_path:
                    known_children.setdefault(parent_path, set()).add(path)

        promo_context = PromotionContext(
            valid_question_paths=valid_question_paths,
            known_children=known_children
        )

        for idx, match in enumerate(all_potential_matches):
            raw_header = text[match.start():match.end()]
            normalized_header = match.group(0)

            # 1. Check if Working Notes section marker appears in gap between previous match end and current match start
            gap_text = normalized_text[prev_match_end:match.start()]
            if any(re.search(pat, gap_text, re.MULTILINE) for pat in WORKING_NOTE_SECTION_PATTERNS):
                parser_state = ParserState.WORKING_NOTES
                working_notes_start_offset = match.start()
                last_working_note_offset = match.start()
                last_working_note_num = 0

            # 2. Skip matches that are explicit Working Note headers (e.g. "Working Note 1", "W.N. 1")
            if any(re.search(pat, raw_header) for pat in WORKING_NOTE_HEADER_PATTERNS):
                logger.info("Answer candidate rejected | candidate=%r | reason=explicit Working Note header | start_offset=%d", raw_header, match.start())
                diagnostics.rejected_headers.append({
                    "header": raw_header,
                    "reason": "explicit Working Note header"
                })
                prev_match_end = match.end()
                continue

            # 3. Handle Working Notes zone state transitions & self-healing recovery
            path = self.normalizer.normalize_header(normalized_header)

            if parser_state == ParserState.WORKING_NOTES:
                is_strong = self.validator.is_strong_header(raw_header)
                c_main, _, _ = HierarchyUtils.decompose_path(path)
                s_main, _, _ = HierarchyUtils.decompose_path(hierarchy_stack)
                c_num = int(c_main) if c_main and c_main.isdigit() else 0
                s_num = int(s_main) if s_main and s_main.isdigit() else 0

                is_working_note = False
                if c_num > 0:
                    is_working_note = (c_num <= s_num) or (last_working_note_num > 0 and c_num == last_working_note_num + 1) or (last_working_note_num == 0 and c_num == 1)

                # Self-healing recovery if character distance threshold from last working note exceeded
                ref_offset = last_working_note_offset if last_working_note_offset > 0 else working_notes_start_offset
                distance_exceeded = (match.start() - ref_offset) > max_wn_len

                if is_strong or distance_exceeded or not is_working_note:
                    parser_state = ParserState.DEFAULT
                    working_notes_start_offset = 0
                    last_working_note_offset = 0
                    last_working_note_num = 0
                    if distance_exceeded:
                        logger.warning("Working Notes zone auto-recovered due to max distance threshold | start_offset=%d", match.start())
                else:
                    logger.info("Answer candidate rejected | candidate=%r | reason=item inside Working Notes section | start_offset=%d", raw_header, match.start())
                    diagnostics.rejected_headers.append({
                        "header": raw_header,
                        "reason": "item inside Working Notes section"
                    })
                    if c_num > 0:
                        last_working_note_num = c_num
                        last_working_note_offset = match.start()
                    prev_match_end = match.end()
                    continue


            # 4. Check if this match falls inside a structured block (table region)
            inside_block = self._is_inside_structured_block(match.start(), normalized_text)
            if context:
                context.inside_structured_block = inside_block
            if inside_block:
                logger.info("Answer candidate rejected | candidate=%r | reason=inside structured block | start_offset=%d", raw_header, match.start())
                diagnostics.rejected_headers.append({
                    "header": raw_header,
                    "reason": "inside structured block"
                })
                prev_match_end = match.end()
                continue
                    
            # 5. Pure structural and hierarchy validation using HeaderValidator
            result = self.validator.is_valid(match, path, hierarchy_stack, normalized_text)
            if result.is_valid:
                # Context-aware list item rejection via weighted heuristics
                next_match_start = all_potential_matches[idx+1].start() if idx + 1 < len(all_potential_matches) else len(normalized_text)
                evaluation = self._evaluate_promotion(
                    match,
                    path,
                    hierarchy_stack,
                    normalized_text,
                    next_match_start,
                    promo_context
                )
                
                if not evaluation.accepted:
                    temp_stack = list(hierarchy_stack)
                    HierarchyUtils.update_hierarchy_stack(temp_stack, path)
                    logger.info(
                        "Answer candidate rejected | candidate=%r | candidate_path=%s | parent_stack=%s | decision=%s | offset=%d",
                        raw_header, temp_stack, hierarchy_stack, evaluation.reason.name, match.start()
                    )
                    diagnostics.rejected_headers.append({
                        "header": raw_header,
                        "reason": evaluation.reason.name,
                        "offset": match.start()
                    })
                    prev_match_end = match.end()
                    continue

                old_stack = list(hierarchy_stack)
                HierarchyUtils.update_hierarchy_stack(hierarchy_stack, path)
                logger.debug(
                    "Hierarchy stack transition (Answer) | old_stack=%s | new_stack=%s | header=%s | start_offset=%d",
                    old_stack, hierarchy_stack, normalized_header, match.start()
                )
                validated_matches.append((match, list(hierarchy_stack)))
                prev_match_end = match.end()
            else:
                reason_str = result.reason or "Unknown rejection"
                logger.info(
                    "Answer candidate rejected | candidate=%r | reason=%s | start_offset=%d",
                    raw_header, reason_str, match.start()
                )
                diagnostics.rejected_headers.append({
                    "header": raw_header,
                    "reason": reason_str
                })
                prev_match_end = match.end()






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

        # Parse any structured tables inside MCQ sections
        mcq_table_answers = self._parse_mcq_tables(
            normalized_text,
            text,
            sections,
            page_offsets,
            base_offset,
            page_keys
        )
        parsed_answers.extend(mcq_table_answers)
        
        # Deduplicate parsed answers by hierarchy path to avoid ambiguous matching conflicts
        seen_answers = {}
        for ans in parsed_answers:
            path_key = tuple(ans.hierarchy_path)
            if path_key not in seen_answers:
                seen_answers[path_key] = ans
            else:
                existing = seen_answers[path_key]
                # Conflict resolution rules:
                # 1. Prefer MCQ Table parser over descriptive regex parser
                # 2. Otherwise, prefer the one with longer text length
                # 3. If text lengths are equal, prefer the one starting earlier in the document
                if ans.source is AnswerSource.MCQ_TABLE and existing.source is not AnswerSource.MCQ_TABLE:
                    seen_answers[path_key] = ans
                elif existing.source is AnswerSource.MCQ_TABLE and ans.source is not AnswerSource.MCQ_TABLE:
                    pass  # Keep existing (mcq_table wins)
                else:
                    len_ans = len(ans.text) if ans.text else 0
                    len_existing = len(existing.text) if existing.text else 0
                    if len_ans > len_existing:
                        seen_answers[path_key] = ans
                    elif len_ans == len_existing:
                        if ans.start_offset < existing.start_offset:
                            seen_answers[path_key] = ans

        parsed_answers = list(seen_answers.values())
        parsed_answers.sort(key=lambda x: x.start_offset)
            
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

    def _is_inside_structured_block(self, start_idx: int, text: str) -> bool:
        last_start = text.rfind("[STRUCTURED_START]", 0, start_idx)
        if last_start == -1:
            return False
        last_end = text.rfind("[STRUCTURED_END]", 0, start_idx)
        return last_start > last_end

    def _parse_mcq_tables(
        self,
        normalized_text: str,
        text: str,
        sections: List[Tuple[int, AnswerSectionType]],
        page_offsets: List[Tuple[int, int]],
        base_offset: int,
        page_keys: List[int],
    ) -> List[ParsedAnswer]:
        """
        Parses all structured tables within the MCQ_ANSWER sections and returns ParsedAnswer objects.
        """
        import re
        from .types import ParsedAnswer, AnswerSectionType, AnswerSource

        mcq_answers: List[ParsedAnswer] = []
        table_pattern = re.compile(r"\[STRUCTURED_START\](.*?)\[STRUCTURED_END\]", re.DOTALL)
        sep_pat = re.compile(r"^[|\s\-:]+$")
        q_num_pat = re.compile(r"^\s*(\d+)\s*\.?\s*$")
        opt_pat = re.compile(r"(?i)\bOption\b|\([a-eA-E]\)|\bAns\.?\b")
        data_table_header_pat = re.compile(
            r"(?i)\b(Particulars|Description|Details|Debit|Credit|Dr|Cr|Amount|Balance|Schedule|"
            r"Asset|Liability|Equity|Revenue|Expense|Shares|Cost|Carrying|Penalty|Fine|Offence|"
            r"Compliance|Audit|CGST|SGST|IGST|Taxable|Exemption|Deduction|Frequency|Probability|"
            r"Variance|Ratio|Demand|Supply|Output|Variable|Parameter|Specification|Input|State|"
            r"Condition|Status|Difference|Distinction|Feature|Advantage|Disadvantage|Merit|Demerit|"
            r"Category|Classification|Remarks|Summary|Item No|Basis of)\b"
        )

        for match in table_pattern.finditer(normalized_text):
            table_start = match.start()
            if self._get_section_type(table_start, sections) != AnswerSectionType.MCQ_ANSWER:
                continue

            table_content = match.group(1).strip()
            table_lines = [l.strip() for l in table_content.split("\n") if l.strip() and not sep_pat.match(l.strip())]
            has_mcq_sig = any(opt_pat.search(cell) for line in table_lines for cell in line.split("|"))
            if table_lines and data_table_header_pat.search(table_lines[0]) and not has_mcq_sig:
                # Skip descriptive/financial solution data tables from MCQ answer key parsing
                continue

            raw_rows = []
            local_offset = len("[STRUCTURED_START]")
            last_opt_col_idx = None
            explicit_opt_count = 0

            for line in match.group(1).strip().split("\n"):
                line_len = len(line) + 1
                line_stripped = line.strip()
                if not line_stripped or sep_pat.match(line_stripped):
                    local_offset += line_len
                    continue

                cells = [c.strip() for c in line.split("|")]
                if cells and not cells[0]: cells.pop(0)
                if cells and not cells[-1]: cells.pop()
                if not cells:
                    local_offset += line_len
                    continue

                # Strip asterisks before matching the question number
                q_num = None
                for cell in cells:
                    clean_c = cell.replace("*", "").strip()
                    m = q_num_pat.match(clean_c)
                    if m:
                        q_num = m.group(1)
                        break
                
                # Search for option cell matching opt_pat
                opt_content = None
                for idx, cell in enumerate(cells):
                    if opt_pat.search(cell):
                        opt_content, last_opt_col_idx = cell, idx
                        explicit_opt_count += 1
                        break

                # Fallback matching
                if q_num and not opt_content:
                    if last_opt_col_idx is not None and last_opt_col_idx < len(cells):
                        cell = cells[last_opt_col_idx]
                        if re.sub(r'<br\s*/?>', '', cell).strip():
                            opt_content = cell
                    if not opt_content:
                        for cell in cells:
                            clean_cell = re.sub(r'<br\s*/?>', '', cell).strip()
                            # Strip asterisks here as well for consistency
                            clean_c = clean_cell.replace("*", "").strip()
                            if clean_cell and not q_num_pat.match(clean_c):
                                opt_content = cell
                                break

                raw_rows.append({
                    "q_num": q_num,
                    "content": opt_content,
                    "offset": base_offset + table_start + local_offset,
                    "length": line_len
                })
                local_offset += line_len

            # Aggregate multi-line content
            table_answers = []
            current_q_num, current_parts, current_start, current_end = None, [], None, None

            def save_aggregated():
                if current_q_num and current_parts:
                    full_txt = re.sub(r'\s+', ' ', " ".join(current_parts).strip()).replace("**", "")
                    start_page = HierarchyUtils.get_page_num_fast(current_start, page_offsets, page_keys)
                    end_page = HierarchyUtils.get_page_num_fast(current_end - 1, page_offsets, page_keys)
                    table_answers.append(ParsedAnswer(
                        hierarchy_path=[current_q_num],
                        raw_header=f"\n{current_q_num}.",
                        text=full_txt,
                        start_offset=current_start,
                        end_offset=current_end,
                        start_page=start_page,
                        end_page=end_page,
                        section_type=AnswerSectionType.MCQ_ANSWER,
                        source=AnswerSource.MCQ_TABLE
                    ))

            for row in raw_rows:
                if row["q_num"]:
                    if current_q_num and current_q_num != row["q_num"]:
                        save_aggregated()
                        current_parts, current_start = [], None
                    current_q_num = row["q_num"]
                    if current_start is None: current_start = row["offset"]
                    current_end = row["offset"] + row["length"]
                    if row["content"]: current_parts.append(row["content"])
                elif current_q_num and row["content"]:
                    current_parts.append(row["content"])
                    current_end = row["offset"] + row["length"]

            save_aggregated()

            # Require at least 1 explicit option cell match to recognize the block as an MCQ table.
            # This is safe because:
            # 1. The method only processes tables inside MCQ_ANSWER sections.
            # 2. It requires at least one option prefix (e.g. "Option (a)", "(c)") in the cells.
            # 3. Descriptive/financial tables (e.g. Balance Sheet) contain 0 option prefixes,
            #    giving them explicit_opt_count = 0, so they are correctly ignored.
            if explicit_opt_count >= 1:
                    mcq_answers.extend(table_answers)

        return mcq_answers

    def _evaluate_promotion(
        self,
        match: re.Match,
        path: List[str],
        hierarchy_stack: List[str],
        text: str,
        next_match_start: int,
        context: PromotionContext
    ) -> PromotionEvaluation:
        c_main, c_alpha, c_roman = HierarchyUtils.decompose_path(path)
        s_alpha = HierarchyUtils.decompose_path(hierarchy_stack)[1]
        s_roman = HierarchyUtils.decompose_path(hierarchy_stack)[2]

        # Calculate potential path after promotion
        temp_stack = list(hierarchy_stack)
        HierarchyUtils.update_hierarchy_stack(temp_stack, path)
        potential_path = tuple(temp_stack)

        # 1. Question Structure Check (Authoritative when child information is present)
        if context.valid_question_paths is not None and context.known_children is not None:
            parent_path = tuple(hierarchy_stack) if hierarchy_stack else None
            if parent_path and parent_path in context.known_children:
                children = context.known_children[parent_path]
                if children:
                    if potential_path in children:
                        return PromotionEvaluation(True, PromotionReason.ACCEPT_QUESTION_STRUCTURE)
                    else:
                        return PromotionEvaluation(False, PromotionReason.REJECT_QUESTION_STRUCTURE)

        # 2. Sequence Rule (Only when entering a new depth)
        if c_alpha and s_alpha is None:
            if c_alpha != 'a':
                return PromotionEvaluation(False, PromotionReason.REJECT_SEQUENCE_START)
        elif c_roman and s_roman is None:
            if c_roman != 'i':
                return PromotionEvaluation(False, PromotionReason.REJECT_SEQUENCE_START)

        # 3. Colon/List context heuristic (evidence of inline list)
        if c_alpha or c_roman:
            last_char = self._get_last_non_whitespace_char(text, match.start())
            preceded_by_colon = (last_char == ':')
            
            if preceded_by_colon:
                # Lazy calculation of candidate block only if colon check is hit
                candidate_block = text[match.end():next_match_start]
                clean_block = candidate_block.replace('\r', '')
                
                # Structural check: no paragraph breaks and length is relatively short
                looks_like_inline_list = ("\n\n" not in clean_block) and (len(clean_block) < 1000)
                
                if looks_like_inline_list:
                    return PromotionEvaluation(False, PromotionReason.REJECT_INLINE_LIST)

        return PromotionEvaluation(True, PromotionReason.ACCEPT)

    def _get_last_non_whitespace_char(self, text: str, start_idx: int) -> str:
        idx = start_idx - 1
        while idx >= 0:
            char = text[idx]
            if char not in (' ', '\t', '\n', '\r'):
                return char
            idx -= 1
        return ""


