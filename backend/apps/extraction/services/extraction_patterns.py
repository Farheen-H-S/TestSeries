import re
from .constants import DEFAULT_SEMANTIC_SCORE_THRESHOLD

# Section Delimiters for Layout Detection
ANSWER_SECTION_DELIMITERS = [
    r"SUGGESTED ANSWERS",
    r"SUGGESTED ANSWER",
    r"ANSWERS TO QUESTIONS",
    r"ANSWERS",
    r"SOLUTIONS",
    r"HINTS",
    r"ANSWER KEY",
    r"MODEL ANSWERS",
    r"SUGGESTED SOLUTION"
]

MCQ_ANSWER_SECTION_PATTERNS = [
    r"(?i)^[ \t]*(?:Answers?\s+to\s+)?Multiple\s+Choice\s+Questions(?:\s+Answers?)?",
    r"(?i)^[ \t]*MCQ\s+Answers?",
    r"(?i)^[ \t]*Part\s+[I|A|B|1|2][-–—\s:]*(?:Multiple\s+Choice\s+Questions|MCQ\s+Answers?)",
    r"(?i)^[ \t]*ANSWERS?\s+TO\s+(?:MULTIPLE\s+CHOICE\s+QUESTIONS|MCQS?)",
]

WORKING_NOTE_SECTION_PATTERNS = [
    r"(?i)^[ \t]*Working\s+Notes?(?:\s*[:\-–—])?",
    r"(?i)^[ \t]*W\.?N\.?\s*(?:\d+|[:\-–—])",
    r"(?i)^[ \t]*Illustrations?(?:\s*[:\-–—])?",
    r"(?i)^[ \t]*Annexures?(?:\s*[:\-–—])?",
    r"(?i)^[ \t]*Appendix(?:\s*[:\-–—])?",
]


WORKING_NOTE_HEADER_PATTERNS = [
    r"(?i)^[ \t]*(?:Working\s+Note|W\.?N\.?)\s*(\d+)(?:\s*[:\-–—\.]?\s*(.*?))?$",
]

DOCUMENT_METADATA_PATTERNS = [
    r"(?i)^[ \t]*Part\s+[I|V|X\d]+[-–—\s]+(?:Questions|Multiple\s+Choice\s+Questions|Descriptive\s+Questions)(?:\s+and\s+Answers)?\s*$",
    r"(?i)^[ \t]*Part\s+[I|V|X\d]+[-–—\s]+Answers?\s*$",
    r"(?i)^[ \t]*QUESTIONS?\s*$",
    r"(?i)^[ \t]*ANSWERS?\s*$",
    r"(?i)^[ \t]*SUGGESTED\s+ANSWERS?\s*$",
    r"(?i)^[ \t]*SUGGESTED\s+SOLUTIONS?\s*$",
    r"(?i)^[ \t]*REVISION\s+TEST\s+PAPERS?\s*$",
    r"(?i)^[ \t]*MOCK\s+TEST\s+PAPERS?\s*$",
    r"(?i)^[ \t]*MODEL\s+TEST\s+PAPERS?\s*$",
    r"(?i)^[ \t]*(?:FINAL|INTERMEDIATE|FOUNDATION)\s+(?:EXAMINATION|EXAMS?|COURSE)\s*$",
    r"(?i)^[ \t]*FINAL\s+COURSE\s*$",
    r"(?i)^[ \t]*(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)?\s*\d{4}\s+(?:EXAMINATION|EXAMS?)\s*$",
    r"(?i)^[ \t]*PAPER\s*[-–—:]\s*\d+[\s\-–—:]*.*$",
    r"(?i)^[ \t]*(?:FINANCIAL\s+REPORTING|ADVANCED\s+AUDITING|CORPORATE\s+AND\s+ECONOMIC\s+LAWS|DIRECT\s+TAX|INDIRECT\s+TAX|STRATEGIC\s+FINANCIAL\s+MANAGEMENT|AUDITING\s+AND\s+ETHICS|TAXATION|COST\s+AND\s+MANAGEMENT\s+ACCOUNTING)\s*$",
    r"(?i)^[ \t]*(?:Time\s+Allowed|Maximum\s+Marks|Max\s+Marks).*$",
    r"(?i)^[ \t]*General\s+Instructions.*$",
    r"(?i)^[ \t]*Roll\s+No.*$",
]

MAIN_ANSWER_SECTION_PATTERNS = [
    r"(?i)^[ \t]*Suggested\s+Answers?",
    r"(?i)^[ \t]*Suggested\s+Solutions?",
    r"(?i)^[ \t]*Answers?\s+to\s+Questions?",
    r"(?i)^[ \t]*Solutions?",
    r"(?i)^[ \t]*Part\s+II[-–—\s]+Descriptive\s+Questions",
]



# Question Header Patterns
# Matches: Question 1, Q1, Q.1, 1., 1.1, 1(a), (a), (i)
QUESTION_HEADER_PATTERNS = [
    r"^[ \t]*([1-9])\.([1-9]|1[0-5])[ \t]*$",                                 # 1.1, 1.2, 2.1 (Case study decimal questions 1.1 to 9.15)
    r"(?i)^[ \t]*Question\s+(?:No\.\s*)?(\d+)(?:[ \t]*\([^)]+\))*",          # Question 1, Question 1(a), Question 1(a)(i)
    r"(?i)^[ \t]*Q\.?\s?(\d+)(?:[ \t]*\([^)]+\))*",                          # Q1, Q. 1, Q1(a)
    r"^[ \t]*(\d{1,2})[.)](?!\d)(?:[ \t]*\([^)]+\))*",                       # 1. or 1) or 1.(a) (max 99)
    r"^[ \t]*\(([a-zA-Z])\)",                                                # (a)
    r"^[ \t]*\(([ivxIVX]+)\)(?!\s*e\.)",                                     # (i), (ii), (iv)
    r"^[ \t]*\d{1,2}\s*\(([a-z])\)",                                         # 1(a)
    r"^[ \t]*([a-z])\s*[.)](?!\s*e\.)(?![a-zA-Z])",                         # a. or a)
]

# Answer Header Patterns
# Matches: Answer to Question 1, Ans. 1, Solution 1, 1.1, or just 1. in Answer section
ANSWER_HEADER_PATTERNS = [
    r"^[ \t]*([1-9])\.([1-9]|1[0-5])[ \t]*$",                                         # 1.1, 1.2, 2.1
    r"(?i)^\s*Answer\s+(?:to\s+)?(?:Question\s+)?(?:No\.\s*)?(\d+)(?:\(([a-z])\))?", # Answer to Question 1(a)
    r"(?i)^\s*Ans\.?\s*(\d+)(?:\(([a-z])\))?",                                       # Ans. 1(a)
    r"(?i)^\s*Solution\s*(\d+)(?:\(([a-z])\))?",                                     # Solution 1(a)
    r"(?i)^\s*(?:Question|Q\.?)\s*(?:No\.\s*)?(\d+)(?:\(([a-z])\))?",                # Question 1 or Q1
    r"^\s*(\d{1,2})[.)](?!\d)(?:\s*\(([a-z])\))?",                                   # 1. or 1.(a)
    r"^\s*\(([a-zA-Z])\)",                                                           # (a)
    r"^\s*\(([ivxIVX]+)\)(?!\s*e\.)",                                                # (i), (ii), (iv)
]


# Marks Extraction Patterns
MARKS_PATTERNS = [
    r"\(\s*(\d+)\s*marks?\s*\)",           # (5 Marks)
    r"\[\s*(\d+)\s*marks?\s*\]",           # [5 Marks]
    r"\bmarks?\s*[:\-–—]\s*(\d+)\b",       # Marks: 5 or Marks - 5
    r"\b(\d+)\s*marks?\b",                 # 5 Marks
    r"\(\s*(\d+)\s*\)",                    # (5)
    r"\[\s*(\d+)\s*\]",                    # [5]
    r"(?:^|[\n\r.?])\s*(\d+)\s*m\b(?=\s*(?:[.)\]?:\-\–—\n\r]|$))"  # 5M or 5 M
]

# Marks Exclusion Patterns (To avoid False Positives)
MARKS_EXCLUSION_PATTERNS = [
    r"\b(20\d{2}|19\d{2})\b",                 # Years
    r"\b(?:Ind\s+AS|AS|SA|CARO)\s+\d+(?:\s*\([a-zA-Z0-9]+\))*(?!\w)",     # Standards
    r"\b(?:Sec|Section)\.?\s+\d+[A-Z]*(?:\s*\([a-zA-Z0-9]+\))*(?!\w)",     # Sections
    r"\b(?:Page|P)\.?\s*\d+\b",               # Page numbers
    r"\b(?:Question|Q)\.?\s*\d+\b",           # Question numbers
]

# Instruction Priority List
INSTRUCTION_PRIORITY = [
    "CALCULATE",
    "COMPUTE",
    "PREPARE",
    "JOURNALIZE",
    "RECONCILE",
    "ANALYSE",
    "EXPLAIN",
    "DISCUSS",
    "DEFINE",
    "STATE",
    "LIST",
    "IDENTIFY"
]

# Classification Rules
# Rules are (Type, Keyword List)
CLASSIFICATION_RULES = {
    "PRACTICAL": [
        "CALCULATE", "COMPUTE", "PREPARE", "JOURNALIZE", "JOURNALISE", "LEDGER", 
        "BALANCE SHEET", "PROFIT AND LOSS", "RECONCILE", "TOTAL INCOME", "TAX LIABILITY",
        "TAX PAYABLE", "CASH FLOW", "NET PROFIT", "CAPITAL GAINS", "COST OF CAPITAL",
        "ARM'S LENGTH PRICE"
    ],
    "THEORY": [
        "EXPLAIN", "DISCUSS", "DEFINE", "STATE", "LIST", "DISTINGUISH", 
        "DIFFERENTIATE", "COMPARE", "DESCRIBE", "ENUMERATE", "COMMENT",
        "EXAMINE WHETHER", "ADVISE", "WHAT ARE THE", "REPORTING REQUIREMENTS",
        "CRITICALLY EXAMINE", "VALIDITY"
    ],
    "CASE_STUDY": [
        "CASE SCENARIO", "CASE STUDY", "INTEGRATED CASE SCENARIO", "CASE SCENARIOS"
    ],
    "OBJECTIVE": [
        "TRUE OR FALSE", "MULTIPLE CHOICE", "MCQ", "CHOOSE THE CORRECT", "CHOOSE THE MOST APPROPRIATE"
    ]
}
# Compiled Patterns (Individual to preserve anchors)
COMPILED_SECTION_DELIMITERS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in ANSWER_SECTION_DELIMITERS]
COMPILED_QUESTION_HEADER_PATTERNS = [re.compile(p, re.MULTILINE) for p in QUESTION_HEADER_PATTERNS]
COMPILED_ANSWER_HEADER_PATTERNS = [re.compile(p, re.MULTILINE) for p in ANSWER_HEADER_PATTERNS]
COMPILED_MARKS_PATTERNS = [re.compile(p, re.IGNORECASE) for p in MARKS_PATTERNS]
COMPILED_MARKS_EXCLUSION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in MARKS_EXCLUSION_PATTERNS]

COMPILED_QUESTION_START_PATTERNS = [
    re.compile(r"(?i)Part\s+II[-–—\s]+Questions(?:\s+and\s+Answers)?"),
    re.compile(r"(?im)^[ \t]*QUESTIONS[ \t]*$"),
    re.compile(r"(?i)\bQuestions\s+1\s+to\s+\d+\b"),
]


def get_default_parser_config():
    from .types import ParserConfig
    return ParserConfig(
        section_delimiters=COMPILED_SECTION_DELIMITERS,
        question_header_patterns=COMPILED_QUESTION_HEADER_PATTERNS,
        answer_header_patterns=COMPILED_ANSWER_HEADER_PATTERNS,
        case_study_keywords=CLASSIFICATION_RULES["CASE_STUDY"],
        instruction_priority=INSTRUCTION_PRIORITY,
        marks_patterns=COMPILED_MARKS_PATTERNS,
        marks_exclusion_patterns=COMPILED_MARKS_EXCLUSION_PATTERNS,
        semantic_score_threshold=DEFAULT_SEMANTIC_SCORE_THRESHOLD,
        question_start_patterns=COMPILED_QUESTION_START_PATTERNS
    )
