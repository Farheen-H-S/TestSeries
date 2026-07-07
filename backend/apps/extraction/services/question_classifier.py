import re
from dataclasses import dataclass
from typing import List, Dict
from .extraction_patterns import CLASSIFICATION_RULES

@dataclass
class ClassificationRule:
    type_name: str
    patterns: List[re.Pattern]
    priority: int

class QuestionClassifier:
    """
    Data-driven question type classifier.
    """
    
    def __init__(self, rules_dict: Dict[str, List[str]] = None):
        source_rules = rules_dict or CLASSIFICATION_RULES
        self.rules: List[ClassificationRule] = []
        
        # Convert dict to ordered rule objects
        # Assign priorities: CASE_STUDY > PRACTICAL > THEORY > OBJECTIVE
        priority_map = {
            "CASE_STUDY": 100,
            "PRACTICAL": 80,
            "THEORY": 60,
            "OBJECTIVE": 40
        }
        
        for type_name, keywords in source_rules.items():
            patterns = []
            for kw in keywords:
                kw_upper = kw.upper()
                # Robust boundary matching for keywords (including trailing punctuation like MR. or DR.)
                start_boundary = r"\b" if kw_upper[0].isalnum() or kw_upper[0] == '_' else ""
                end_boundary = r"\b" if kw_upper[-1].isalnum() or kw_upper[-1] == '_' else r"(?!\w)"
                pattern_str = f"{start_boundary}{re.escape(kw_upper)}{end_boundary}"
                patterns.append(re.compile(pattern_str))
                
            self.rules.append(ClassificationRule(
                type_name=type_name,
                patterns=patterns,
                priority=priority_map.get(type_name, 0)
            ))
            
        # Sort by priority desc
        self.rules.sort(key=lambda x: x.priority, reverse=True)

    def classify(self, text: str) -> str:
        """
        Evaluates rules in priority order.
        """
        upper_text = text.upper()
        
        for rule in self.rules:
            for pattern in rule.patterns:
                if pattern.search(upper_text):
                    return rule.type_name
                    
        return "UNIDENTIFIED"
