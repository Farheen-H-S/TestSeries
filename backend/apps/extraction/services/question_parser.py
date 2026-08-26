import re
import logging
from typing import List, Optional, Dict, Any, Tuple
from .types import ParsedQuestion, QuestionLevel, ParserConfig, ParsingDiagnostics, QuestionParseResult, ParsingContext
from .normalizer import Normalizer
from .header_validator import HeaderValidator
from .hierarchy_utils import HierarchyUtils

logger = logging.getLogger(__name__)


class QuestionParser:
    """
    Greedy, hierarchy-aware parser for extracting question blocks.
    Delegates validation to HeaderValidator and uses binary search for performance.
    """
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.normalizer = Normalizer()
        self.validator = HeaderValidator()
        self.diagnostics = ParsingDiagnostics()
        self.semantic_score_threshold = getattr(config, 'semantic_score_threshold', 2)

    def parse(
        self,
        text: str,
        page_offsets: List[Tuple[int, int]],
        base_offset: int = 0,
        enable_semantic_validation: bool = False,
        context: Optional[ParsingContext] = None
    ) -> List[ParsedQuestion]:
        """
        Parses text into a list of hierarchical questions with strict validation and offset correction.
        """
        result = self.parse_with_diagnostics(text, page_offsets, base_offset, enable_semantic_validation, context)
        self.diagnostics = result.diagnostics
        return result.questions



    def parse_with_diagnostics(
        self,
        text: str,
        page_offsets: List[Tuple[int, int]],
        base_offset: int = 0,
        enable_semantic_validation: bool = False,
        context: Optional[ParsingContext] = None
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
        
        context = context or ParsingContext()
        
        i = 0
        while i < len(all_potential_matches):
            match = all_potential_matches[i]
            
            # Check if this match starts an MCQ sequence of options
            if self._is_mcq_sequence_detected(all_potential_matches, i, normalized_text):
                context.inside_mcq_sequence = True
                
                m0 = all_potential_matches[i]
                norm0 = self.normalizer.normalize_header(m0.group(0))
                m1_norm = self.normalizer.normalize_header(all_potential_matches[i+1].group(0)) if i + 1 < len(all_potential_matches) else None
                
                norm0_alpha = norm0[-1] if norm0 else ''
                m1_alpha = m1_norm[-1] if m1_norm else ''
                
                # If norm0_alpha == 'a' and m1_alpha == 'c' (embedded b in table), we skip 3 matches (a, c, d), otherwise 4
                skip_count = 3 if (norm0_alpha == 'a' and m1_alpha == 'c') else 4

                # Reject/skip option matches
                for skip_offset in range(skip_count):
                    if i + skip_offset < len(all_potential_matches):
                        opt_match = all_potential_matches[i + skip_offset]
                        raw_opt_header = text[opt_match.start():opt_match.end()]
                        logger.debug("Ignoring MCQ option candidate: %s", raw_opt_header)
                        diagnostics.rejected_headers.append({
                            "header": raw_opt_header,
                            "reason": "MCQ option sequence detected"
                        })
                i += skip_count
                continue
                
            # Check if this match falls inside a structured block (table region)
            if self._is_inside_structured_block(match.start(), normalized_text):
                context.inside_structured_block = True
                raw_header = text[match.start():match.end()]
                logger.debug("Ignoring candidate inside structured block: %s", raw_header)
                diagnostics.rejected_headers.append({
                    "header": raw_header,
                    "reason": "inside structured block"
                })
                i += 1
                continue
            else:
                context.inside_structured_block = False
                
            # Check if a new Case Scenario or major section heading occurred in gap since previous validated match
            prev_end = validated_matches[-1][0].end() if validated_matches else 0
            gap_since_prev = normalized_text[prev_end:match.start()]
            has_case_heading = bool(re.search(r"(?im)^[ \t]*(?:Case\s+(?:Scenario|Study)\b|(?:PART|SECTION|DIVISION)\s*[-–—:]?\s*[A-Z\d]+)", gap_since_prev))
            if has_case_heading:
                hierarchy_stack.clear()
                context.inside_mcq_sequence = False
                
            normalized_header = match.group(0)
            path = self.normalizer.normalize_header(normalized_header)
            
            # Reset inside_mcq_sequence if a main question is encountered
            candidate_level = self.validator._get_candidate_level(path)
            if candidate_level == "main":
                context.inside_mcq_sequence = False
                
            # If a new case scenario started and this candidate is a sub-item bullet point, ignore it as scenario narrative
            if has_case_heading and candidate_level != "main":
                i += 1
                continue

            # Main question monotonicity check across whole document:
            # Prevent regressions (e.g. 1. 2. 3. inside Case Scenario II preamble after Question 6)
            if candidate_level == "main" and len(path) == 1 and path[0].isdigit():
                validated_mains = [int(p[0]) for _, p in validated_matches if p and len(p) >= 1 and p[0].isdigit()]
                if validated_mains:
                    highest_main_num = max(validated_mains)
                    cand_num = int(path[0])
                    if cand_num <= highest_main_num:
                        diagnostics.rejected_headers.append({
                            "header": text[match.start():match.end()],
                            "reason": f"regression of main question number ({cand_num} <= {highest_main_num}) inside narrative/case scenario"
                        })
                        i += 1
                        continue

            # Reject introductory notes bullets before Question 1 (e.g. Notes - (A), (B), (C) before 1.)
            if candidate_level == "alpha" and not hierarchy_stack:
                has_digit_main_later = any(
                    self.validator._get_candidate_level(self.normalizer.normalize_header(m.group(0))) == "main"
                    for m in all_potential_matches[i+1:]
                )
                if has_digit_main_later:
                    diagnostics.rejected_headers.append({
                        "header": text[match.start():match.end()],
                        "reason": "introductory notes/bullet before Question 1"
                    })
                    i += 1
                    continue
                
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
                    if score < self.semantic_score_threshold:
                        logger.debug("Rejecting non-semantic root question candidate: %s | score=%d | reasons=%s", normalized_header, score, score_reasons)
                        diagnostics.rejected_headers.append({
                            "header": text[match.start():match.end()],
                            "reason": f"non-semantic question block (score: {score}, triggered: {score_reasons})"
                        })
                        i += 1
                        continue
            
            # 2. Structural/Hierarchy Validation
            result = self.validator.is_valid(match, path, hierarchy_stack, normalized_text)
            if result.is_valid:
                # 2.1 Answer-Key-Guided Sub-Question Filtering
                if context and context.valid_question_paths:
                    temp_stack = list(hierarchy_stack)
                    HierarchyUtils.update_hierarchy_stack(temp_stack, path)
                    temp_tuple = tuple(temp_stack)
                    if len(temp_tuple) >= 2:
                        has_exact_or_child = any(
                            vp == temp_tuple or (len(vp) > len(temp_tuple) and vp[:len(temp_tuple)] == temp_tuple)
                            for vp in context.valid_question_paths
                        )
                        if not has_exact_or_child:
                            parent_tuple = temp_tuple[:-1]
                            if parent_tuple in context.valid_question_paths or (temp_tuple[0],) in context.valid_question_paths:
                                raw_header = text[match.start():match.end()]
                                diagnostics.rejected_headers.append({
                                    "header": raw_header,
                                    "reason": "sub-question not present in answer key (unified parent question)"
                                })
                                i += 1
                                continue

                old_stack = list(hierarchy_stack)
                # Update stack to get the full hierarchical path for this question
                HierarchyUtils.update_hierarchy_stack(hierarchy_stack, path)
                if not hierarchy_stack:
                    i += 1
                    continue
                logger.debug(
                    "Hierarchy stack transition | old_stack=%s | new_stack=%s | header=%s | start_offset=%d",
                    old_stack, hierarchy_stack, normalized_header, match.start()
                )
                # Capture current stack state as the path for this question
                validated_matches.append((match, list(hierarchy_stack)))
            else:
                # Use the original header from original text for diagnostics
                raw_header = text[match.start():match.end()]
                diagnostics.rejected_headers.append({
                    "header": raw_header, 
                    "reason": result.reason or "Unknown rejection"
                })
            i += 1

        # Recover un-numbered main questions (e.g. Question 2 Case Study) if context expects main N between N-1 and N+1
        if context and context.valid_question_paths:
            expected_mains = sorted(list(set(int(p[0]) for p in context.valid_question_paths if p and p[0].isdigit())))
            validated_mains = {}
            for idx, (m, h_path) in enumerate(validated_matches):
                if len(h_path) == 1 and h_path[0].isdigit():
                    validated_mains[int(h_path[0])] = (idx, m)
                    
            for n in expected_mains:
                if n not in validated_mains and (n - 1) in validated_mains and (n + 1) in validated_mains:
                    prev_idx, prev_match = validated_mains[n - 1]
                    next_idx, next_match = validated_mains[n + 1]
                    
                    prev_pos = prev_match.start()
                    next_pos = next_match.start()
                    region_text = text[prev_pos:next_pos]
                    
                    # Search for end of previous question's sub-question sequence
                    v_match = list(re.finditer(r'\n\s*V\.\s+', region_text))
                    if v_match:
                        v_start = v_match[0].start()
                        d_match = re.search(r'\(d\).*?(?=\n\s*(?:[A-Z][A-Za-z\s]{3,30}\n|\[STRUCTURED_START\]|\n\s*\n\s*[A-Z]))', region_text[v_start:], re.DOTALL)
                        if d_match:
                            split_offset = v_start + d_match.end()
                        else:
                            d_fallback = re.search(r'\(d\)[^\n]*', region_text[v_start:])
                            split_offset = v_start + d_fallback.end() if d_fallback else v_start
                    else:
                        opt_matches = list(re.finditer(r'\([a-d]\)[^\n]*', region_text))
                        split_offset = opt_matches[-1].end() if opt_matches else 0
                    
                    if split_offset > 0:
                        abs_split_pos = prev_pos + split_offset
                        synth_match_iter = re.search(r'\S', text[abs_split_pos:])
                        if synth_match_iter:
                            actual_pos = abs_split_pos + synth_match_iter.start()
                            
                            class SyntheticMatch:
                                def __init__(self, pos, num_str):
                                    self._pos = pos
                                    self._num_str = num_str
                                def start(self): return self._pos
                                def end(self): return self._pos
                                def group(self, g=0): return f"{self._num_str}."
                                
                            s_match = SyntheticMatch(actual_pos, str(n))
                            validated_matches.append((s_match, [str(n)]))
                            logger.info("Recovered un-numbered main question %d at position %d", n, actual_pos)

        validated_matches.sort(key=lambda x: x[0].start())

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

        # Attach structural shared contexts to question groups
        self._attach_shared_contexts(text, validated_matches, parsed_questions)

        return QuestionParseResult(questions=parsed_questions, diagnostics=diagnostics)

    def _clean_document_metadata(self, text: str) -> str:
        """
        Strips document-level metadata (e.g. Revision Test Paper, Time Allowed: 3 Hours, Roll No, Subject names)
        from preamble text to isolate true shared question context.
        """
        from .extraction_patterns import DOCUMENT_METADATA_PATTERNS
        from .html_formatter import is_subject_metadata
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            is_meta = False
            for pat in DOCUMENT_METADATA_PATTERNS:
                if re.match(pat, stripped):
                    is_meta = True
                    break
            if not is_meta and is_subject_metadata(stripped):
                is_meta = True
            if not is_meta:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _attach_shared_contexts(
        self,
        text: str,
        validated_matches: List[Tuple[re.Match, List[str]]],
        parsed_questions: List[ParsedQuestion]
    ) -> None:
        if not validated_matches or not parsed_questions:
            return

        range_regex_str = r"(?i)(?:Questions?|MCQs?|MCQ\s+Nos?\.?|Q\.?)\s*(?:from\s+)?(\d+)\s+(?:to|-|–|—)\s+(?:Questions?|MCQs?|MCQ\s+Nos?\.?|Q\.?\s*)?(\d+)"

        current_context = None
        min_q_num = None
        max_q_num = None

        # Check preamble before the first question
        first_start = validated_matches[0][0].start()
        preamble_text = text[:first_start].strip()
        if preamble_text:
            # If preamble contains a Case Scenario or explicit Question range, slice from that header
            ctx_start_match = re.search(
                r"(?im)^[ \t]*(?:Case\s+(?:Scenario|Study)\b|(?:(?:Read|Based\s+on|The)\s+.*?\b)?(?:Questions?|MCQs?|MCQ\s+Nos?\.?|Q\.?)\s*(?:from\s+)?\d+\s+(?:to|-|–|—)\s+(?:Q\.?\s*)?\d+)",
                preamble_text
            )
            raw_scenario = preamble_text[ctx_start_match.start():] if ctx_start_match else preamble_text
            cleaned = self._clean_document_metadata(raw_scenario)
            if cleaned:
                # Check for explicit range or Case Scenario / Study in preamble
                range_match = re.search(range_regex_str, preamble_text)
                is_case_scenario = bool(re.search(r"(?i)\bCase\s+(?:Scenario|Study)\b", preamble_text))
                
                if range_match:
                    current_context = cleaned
                    min_q_num = int(range_match.group(1))
                    max_q_num = int(range_match.group(2))
                elif is_case_scenario:
                    current_context = cleaned
                    min_q_num = 1
                    inner_rng = re.search(range_regex_str, cleaned)
                    max_q_num = int(inner_rng.group(2)) if inner_rng else 6
                else:
                    # Preamble without explicit range belongs to the first question
                    if parsed_questions:
                        parsed_questions[0].text = (cleaned + "\n" + parsed_questions[0].text).strip()

        for i, pq in enumerate(parsed_questions):
            main_num = int(pq.hierarchy_path[0]) if (pq.hierarchy_path and pq.hierarchy_path[0].isdigit()) else None
            
            # Check gap before main question i (where i > 0 and pq is a main question)
            if i > 0 and len(pq.hierarchy_path) == 1:
                prev_match = validated_matches[i-1][0]
                curr_match = validated_matches[i][0]
                gap_raw = text[prev_match.end():curr_match.start()]
                
                # Check for shared context headers in gap_raw (explicit Case Scenarios or Question ranges only)
                ctx_match = re.search(
                    r"(?im)^[ \t]*(?:Case\s+(?:Scenario|Study)\b|(?:(?:Read|Based\s+on|The)\s+.*?\b)?(?:Questions?|MCQs?|MCQ\s+Nos?\.?|Q\.?)\s*(?:from\s+)?\d+\s+(?:to|-|–|—)\s+(?:Q\.?\s*)?\d+)",
                    gap_raw
                )
                if ctx_match:
                    # Text before ctx_match belongs to previous question
                    prev_extra = gap_raw[:ctx_match.start()].strip()
                    if prev_extra:
                        parsed_questions[i-1].text = (parsed_questions[i-1].text + "\n" + prev_extra).strip()
                    
                    raw_context = gap_raw[ctx_match.start():].strip()
                    cleaned_context = self._clean_document_metadata(raw_context)
                    if cleaned_context:
                        range_match = re.search(range_regex_str, raw_context)
                        if range_match:
                            current_context = cleaned_context
                            min_q_num = int(range_match.group(1))
                            max_q_num = int(range_match.group(2))
                        elif re.search(r"(?i)\bCase\s+(?:Scenario|Study)\b", raw_context):
                            current_context = cleaned_context
                            min_q_num = main_num
                            inner_rng = re.search(range_regex_str, cleaned_context)
                            max_q_num = int(inner_rng.group(2)) if inner_rng else ((main_num + 5) if main_num is not None else 12)
                        else:
                            current_context = cleaned_context
                            min_q_num = main_num
                            max_q_num = main_num
                elif re.search(r"(?im)^[ \t]*(?:PART|SECTION|DIVISION)\s*[-–—:]?\s*[A-Z\d]+\s*(?:[-–—:]\s*(?:DESCRIPTIVE\s+QUESTIONS|MULTIPLE\s+CHOICE\s+QUESTIONS|CASE\s+SCENARIOS?)|$)", gap_raw):
                    # Section break in gap
                    current_context = None
                    min_q_num = None
                    max_q_num = None
                elif max_q_num is not None and main_num is not None and main_num > max_q_num:
                    current_context = None
                    min_q_num = None
                    max_q_num = None

            # Case scenarios never extend to descriptive questions (Q13+)
            if main_num is not None and main_num > 12:
                current_context = None
                min_q_num = None
                max_q_num = None

            if max_q_num is not None and main_num is not None and main_num > max_q_num:
                current_context = None
                min_q_num = None
                max_q_num = None

            if min_q_num is not None and main_num is not None and main_num < min_q_num:
                pq.shared_context = None
            else:
                pq.shared_context = current_context




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
            score -= 1
            reasons.append("has_negative_notification")
        if re.search(r"(?i)\bamendment\b", text):
            score -= 1
            reasons.append("has_negative_amendment")
        if re.search(r"(?i)\beffective\s+from\b", text):
            score -= 1
            reasons.append("has_negative_effective_from")
        if re.search(r"(?i)\bshall\s+substitute\b", text):
            score -= 2
            reasons.append("has_negative_shall_substitute")
        if re.search(r"(?i)\blegislative\b", text):
            score -= 1
            reasons.append("has_negative_legislative")
            
        return score, reasons

    def _get_level(self, path: List[str]) -> QuestionLevel:
        if len(path) >= 3: return QuestionLevel.SUB_SUB
        if len(path) == 2: return QuestionLevel.SUB
        return QuestionLevel.MAIN

    def _is_mcq_sequence_detected(self, matches: List[re.Match], current_idx: int, text: str) -> bool:
        if current_idx + 3 >= len(matches):
            return False
            
        candidate_paths = []
        for offset in range(4):
            m = matches[current_idx + offset]
            norm = self.normalizer.normalize_header(m.group(0))
            candidate_paths.append(norm)
            
        decomposed = [HierarchyUtils.decompose_path(p) for p in candidate_paths]
        alphas = [d[1] for d in decomposed]
        mains = [d[0] for d in decomposed]
        romans = [d[2] for d in decomposed]
        
        # Verify consecutive 'a', 'b', 'c', 'd'
        expected_seq = ['a', 'b', 'c', 'd']
        is_seq = True
        for offset, expected in enumerate(expected_seq):
            if alphas[offset] != expected or mains[offset] is not None or romans[offset] is not None:
                is_seq = False
                break
                
        # Fallback check for embedded table option (e.g. (b) inside markdown table between (a) and (c))
        if not is_seq and alphas[0] == 'a' and mains[0] is None and romans[0] is None:
            if len(matches) > current_idx + 2:
                if alphas[1] == 'c' and alphas[2] == 'd' and mains[1] is None and mains[2] is None:
                    m0 = matches[current_idx]
                    m1 = matches[current_idx + 1]
                    between_text = text[m0.end():m1.start()]
                    if re.search(r"(?i)\(b\)", between_text):
                        is_seq = True
                
        # Verify consecutive 'i', 'ii', 'iii', 'iv'
        expected_roman_seq = ['i', 'ii', 'iii', 'iv']
        is_roman_seq = True
        for offset, expected in enumerate(expected_roman_seq):
            if romans[offset] != expected or mains[offset] is not None or alphas[offset] is not None:
                is_roman_seq = False
                break
                
        if not is_seq and not is_roman_seq:
            return False
            
        # Parent question stem keyword check
        parent_match = matches[current_idx - 1] if current_idx > 0 else None
        if parent_match:
            parent_text = text[parent_match.end():matches[current_idx].start()].lower()
            mcq_keywords = [
                "option", "choose", "select", "correct", "incorrect", "which of the following",
                "multiple choice", "value of", "amount of", "what would be", "what is", "is mr.",
                "is hdfc", "calculate", "compute"
            ]
            if any(kw in parent_text for kw in mcq_keywords):
                return True
                
        # Option texts check (if no keywords matched)
        option_texts = []
        for offset in range(4):
            m_start = matches[current_idx + offset].end()
            m_end = matches[current_idx + offset + 1].start() if current_idx + offset + 1 < len(matches) else len(text)
            raw_opt = text[m_start:m_end].strip()
            clean_opt = re.split(r'(?i)\n\s*(?:Case\s+(?:Scenario|Study)|PART|SECTION)\b', raw_opt)[0].split("[STRUCTURED_START]")[0].strip()
            option_texts.append(clean_opt)
            
        verbs = r"(?i)\b(Explain|Discuss|Determine|State|Compute|Prepare|Journalise|Describe|Analyse|Evaluate|Identify|Compare|Distinguish)\b"
        for opt_text in option_texts:
            if len(opt_text) > 220:
                return False
            if re.search(verbs, opt_text):
                return False
                
        return True

    def _is_inside_structured_block(self, start_idx: int, text: str) -> bool:
        last_start = text.rfind("[STRUCTURED_START]", 0, start_idx)
        if last_start == -1:
            return False
        last_end = text.rfind("[STRUCTURED_END]", 0, start_idx)
        return last_start > last_end


