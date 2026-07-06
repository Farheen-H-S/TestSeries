import time
from typing import List, Dict, Tuple
from .types import ParsedQuestion, ParsedAnswer, MatchingResult, MatchingDiagnostics

class AnswerMatcher:
    """
    Correlates Questions and Answers using canonical hierarchy paths.
    """
    
    def match(self, questions: List[ParsedQuestion], answers: List[ParsedAnswer]) -> MatchingResult:
        start_time = time.time()
        diagnostics = MatchingDiagnostics()
        
        # Build answer map for quick lookup
        # Key is a tuple representing the hierarchy path
        answer_map: Dict[Tuple[str, ...], List[ParsedAnswer]] = {}
        for a in answers:
            key = tuple(a.hierarchy_path)
            if key not in answer_map:
                answer_map[key] = []
            answer_map[key].append(a)
            
        # Track duplicates
        for key, ans_list in answer_map.items():
            if len(ans_list) > 1:
                diagnostics.duplicate_answer_ids.append("-".join(key))

        matches: List[Tuple[ParsedQuestion, ParsedAnswer]] = []
        matched_q_keys = set()
        
        for q in questions:
            key = tuple(q.hierarchy_path)
            
            if key in answer_map:
                ans_list = answer_map[key]
                
                # Rule: Only match if 1:1. Ambiguous matches are worse than empty ones.
                if len(ans_list) == 1:
                    matches.append((q, ans_list[0]))
                    diagnostics.matched_count += 1
                    matched_q_keys.add(key)
                else:
                    diagnostics.ambiguous_matches.append("-".join(key))
            else:
                diagnostics.unmatched_questions.append("-".join(key))
                
        # Find unmatched answers
        for key in answer_map:
            if key not in matched_q_keys:
                diagnostics.unmatched_answers.append("-".join(key))
                
        diagnostics.processing_time_ms = (time.time() - start_time) * 1000
        
        return MatchingResult(matches=matches, diagnostics=diagnostics)
