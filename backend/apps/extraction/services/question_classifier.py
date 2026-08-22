import re
from dataclasses import dataclass
from typing import List, Dict, Optional
from .extraction_patterns import CLASSIFICATION_RULES

@dataclass
class ClassificationRule:
    type_name: str
    patterns: List[re.Pattern]
    priority: int

class QuestionClassifier:
    """
    High-accuracy question type classifier for CA examination papers.
    Accurately classifies questions into:
    - MCQ (Multiple Choice Questions with options (a), (b), (c), (d) or MCQ answer key)
    - PRACTICAL (Computational, numerical statements, tax/portfolio/income calculations)
    - THEORY (Legal, auditing, accounting standard conceptual analysis, discussions, advice)
    - CASE_STUDY (Integrated multi-question case scenario background)
    """

    def __init__(self, rules_dict: Optional[Dict[str, List[str]]] = None):
        self.custom_rules = rules_dict is not None
        source_rules = rules_dict or CLASSIFICATION_RULES
        self.rules: List[ClassificationRule] = []

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
                start_boundary = r"\b" if kw_upper[0].isalnum() or kw_upper[0] == '_' else ""
                end_boundary = r"\b" if kw_upper[-1].isalnum() or kw_upper[-1] == '_' else r"(?!\w)"
                pattern_str = f"{start_boundary}{re.escape(kw_upper)}{end_boundary}"
                patterns.append(re.compile(pattern_str))

            self.rules.append(ClassificationRule(
                type_name=type_name,
                patterns=patterns,
                priority=priority_map.get(type_name, 0)
            ))

        self.rules.sort(key=lambda x: x.priority, reverse=True)

    def classify(self, text: str, shared_context: Optional[str] = None, answer_text: Optional[str] = None) -> str:
        """
        Classifies question into MCQ, PRACTICAL, THEORY, or CASE_STUDY.
        """
        if not text:
            return "UNIDENTIFIED"

        raw = text.strip()
        upper = raw.upper()

        # If custom rules dict was provided, evaluate custom rules in priority order
        if self.custom_rules:
            for rule in self.rules:
                for pattern in rule.patterns:
                    if pattern.search(upper):
                        return rule.type_name
            return "UNIDENTIFIED"

        # 1. MCQ Detection
        # Check for multiple choice options (a), (b), (c), (d) or inline options or answer key
        has_mcq_4_options = bool(
            re.search(r'(?m)^\s*\([aA]\)\s+', raw) and 
            re.search(r'(?m)^\s*\([bB]\)\s+', raw) and 
            re.search(r'(?m)^\s*\([cC]\)\s+', raw) and 
            re.search(r'(?m)^\s*\([dD]\)\s+', raw)
        )
        has_inline_mcq = bool(re.search(r'\(a\)\s+.*\(b\)\s+.*\(c\)\s+.*\(d\)\s+', raw, re.DOTALL))
        has_mcq_ans = bool(answer_text and re.match(r'^(?:Option\s*)?\([a-dA-D]\)\s*$', answer_text.strip(), re.IGNORECASE))
        has_mcq_heading = bool(re.search(r'(?i)\b(?:MULTIPLE\s+CHOICE\s+QUESTIONS?|CHOOSE\s+THE\s+MOST\s+APPROPRIATE)\b', raw))

        if has_mcq_4_options or has_inline_mcq or has_mcq_ans or (has_mcq_heading and ('(a)' in raw or '(A)' in raw)):
            return "MCQ"

        # 2. Case Study Scenario (Long narrative context without a direct single calculation)
        if ('CASE SCENARIO' in upper or 'CASE STUDY' in upper or 'INTEGRATED CASE' in upper) and len(raw) > 2000:
            if not any(k in upper for k in ['COMPUTE', 'CALCULATE', 'PREPARE', 'JOURNALIZE']):
                return "CASE_STUDY"

        # 3. Practical / Computation Patterns
        practical_pats = [
            r'\b(?:COMPUTE|CALCULATE)\b',
            r'\bPREPARE\s+(?:THE\s+)?(?:STATEMENT|BALANCE\s+SHEET|LEDGER|PROFIT\s+AND\s+LOSS|CASH\s+FLOW|ACCOUNTS?)\b',
            r'\b(?:JOURNAL\s+ENTRIES|JOURNALISE|JOURNALIZE)\b',
            r'\b(?:TOTAL\s+INCOME\s+AND\s+TAX\s+LIABILITY|TAX\s+PAYABLE|TAX\s+LIABILITY|AMOUNT\s+OF\s+CAPITAL\s+GAINS?)\b',
            r'\b(?:DETERMINE\s+THE\s+(?:TAX|INCOME|VALUE|PRICE|GAIN|LOSS|COST|RATIO|BETA|NAV|ARM\'?S?\s+LENGTH))\b',
            r'\bRECONCILE\b'
        ]

        # 4. Theory / Conceptual Patterns
        theory_pats = [
            r'\b(?:EXPLAIN|DISCUSS|STATE|DESCRIBE|ENUMERATE|COMMENT|DISTINGUISH|DIFFERENTIATE|DEFINE)\b',
            r'\b(?:EXAMINE\s+(?:WHETHER|THE\s+TAXABILITY|THE\s+VALIDITY|THE\s+PROVISIONS|THE\s+APPLICABILITY))\b',
            r'\b(?:WHETHER\s+(?:THE\s+ACTION|EXEMPTION|TAX|TDS|ANY\s+VIOLATION|INCOME|TENABLE|VALID|CLAIM))\b',
            r'\b(?:ADVISE|WHAT\s+ARE\s+THE\s+REPORTING\s+REQUIREMENTS)\b',
            r'\b(?:IS\s+THE\s+(?:ACTION|CONTENTION|CLAIM)\s+(?:OF\s+.*)?(?:CORRECT|VALID|TENABLE|JUSTIFIED))\b',
            r'\b(?:BRIEFLY\s+EXPLAIN|STATE\s+THE\s+CONDITIONS)\b'
        ]

        # Check imperative requirements (e.g. at line start or subquestion label)
        imperative_pract = [p for p in practical_pats if re.search(r'(?im)(?:^|[.\n]\s*(?:\([a-z\d]+\)|\d+[.)])?\s*)' + p, raw)]
        imperative_theor = [p for p in theory_pats if re.search(r'(?im)(?:^|[.\n]\s*(?:\([a-z\d]+\)|\d+[.)])?\s*)' + p, raw)]

        # If explicit calculation imperative exists, it is PRACTICAL
        if imperative_pract:
            return "PRACTICAL"

        if imperative_theor and not imperative_pract:
            return "THEORY"

        # General text checks
        is_pract = any(re.search(p, upper) for p in practical_pats)
        is_theor = any(re.search(p, upper) for p in theory_pats)

        if is_pract:
            return "PRACTICAL"
        if is_theor:
            return "THEORY"

        # Rule fallback based on configured rules
        for rule in self.rules:
            for pattern in rule.patterns:
                if pattern.search(upper):
                    if rule.type_name == "OBJECTIVE":
                        return "MCQ"
                    return rule.type_name

        return "THEORY" if len(raw) < 1200 else "PRACTICAL"
