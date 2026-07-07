import time
from typing import List, Dict, Tuple
from .types import ParsedQuestion, ParsedAnswer, MatchingResult, MatchingDiagnostics

class AnswerMatcher:
    """
    Correlates Questions and Answers using canonical hierarchy paths.
    """
    
    def match(self, questions: List[ParsedQuestion], answers: List[ParsedAnswer]) -> MatchingResult:
        """
        Correlates Questions and Answers using canonical hierarchy paths.
        Strictly rejects ambiguous or duplicate mappings to preserve data integrity.
        """
        start_time = time.time()
        diagnostics = MatchingDiagnostics()
        
        # 1. Map Questions and Answers by canonical path
        q_map: Dict[Tuple[str, ...], List[ParsedQuestion]] = {}
        for q in questions:
            key = tuple(q.hierarchy_path)
            q_map.setdefault(key, []).append(q)
            
        a_map: Dict[Tuple[str, ...], List[ParsedAnswer]] = {}
        for a in answers:
            key = tuple(a.hierarchy_path)
            a_map.setdefault(key, []).append(a)

        # 2. Identify Duplicates
        for key, q_list in q_map.items():
            if len(q_list) > 1:
                diagnostics.duplicate_question_ids.append("-".join(key))
                
        for key, a_list in a_map.items():
            if len(a_list) > 1:
                diagnostics.duplicate_answer_ids.append("-".join(key))

        # 3. Perform 1:1 Matching
        matches: List[Tuple[ParsedQuestion, ParsedAnswer]] = []
        
        all_keys = set(q_map.keys()) | set(a_map.keys())
        for key in all_keys:
            qs = q_map.get(key, [])
            as_ = a_map.get(key, [])
            
            key_str = "-".join(key)
            
            if len(qs) == 1 and len(as_) == 1:
                q = qs[0]
                a = as_[0]
                # Prevent self-matching: if their header offsets overlap, they cannot be matched!
                if q.start_offset < a.end_offset and a.start_offset < q.end_offset:
                    diagnostics.unmatched_questions.append(key_str)
                    diagnostics.unmatched_answers.append(key_str)
                else:
                    # Perfect Match
                    matches.append((q, a))
                    diagnostics.matched_count += 1
            elif len(qs) > 0 and len(as_) > 0:
                # Ambiguous: Both exist but not 1:1
                diagnostics.ambiguous_matches.append(key_str)
            elif len(qs) > 0:
                # Unmatched Question
                diagnostics.unmatched_questions.append(key_str)
            elif len(as_) > 0:
                # Unmatched Answer
                diagnostics.unmatched_answers.append(key_str)
                
        diagnostics.processing_time_ms = (time.time() - start_time) * 1000
        
        return MatchingResult(matches=matches, diagnostics=diagnostics)
