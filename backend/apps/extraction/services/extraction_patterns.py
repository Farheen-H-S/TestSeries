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
    r"(?i)(?:^[ \t]*|\b)Working\s+Notes?(?:\s*[:\-–—])?",
    r"(?i)(?:^[ \t]*|\b)W\.?N\.?\s*(?:\d+|[:\-–—])",
    r"(?i)(?:^[ \t]*|\b)Illustrations?(?:\s*[:\-–—])?",
    r"(?i)(?:^[ \t]*|\b)Annexures?(?:\s*[:\-–—])?",
    r"(?i)(?:^[ \t]*|\b)Appendix(?:\s*[:\-–—])?",
]


WORKING_NOTE_HEADER_PATTERNS = [
    r"(?i)^[ \t]*(?:Working\s+Note|W\.?N\.?)\s*(\d+)(?:\s*[:\-–—\.]?\s*(.*?))?$",
    r"(?i)^[ \t]*(?:\d+\.\s*)?(?:Computation\s+of\s+Goodwill|Retained\s+Earnings\s+for\s+CBS|Net\s+Inventory\s+for\s+CBS|Trade\s+Receivables\s+for\s+CBS|Inventory\s+to\s+be\s+shown\s+in\s+CBS|Analysis\s+of\s+Retained\s+Earnings|Apportionment\s+of\s+profit|Non-Controlling\s+Interest\s+as\s+per\s+fair\s+value)\b",
]

KNOWN_SUBJECT_PATTERNS = [
    # CA Final
    r"Financial\s+Reporting",
    r"Advanced\s+Financial\s+Management",
    r"Strategic\s+Financial\s+Management",
    r"Advanced\s+Auditing(?:,\s*Assurance)?\s+and\s+Professional\s+Ethics",
    r"Advanced\s+Auditing(?:,\s*Assurance(?:\s+and)?)?",
    r"(?:Assurance\s+and\s+)?Professional\s+Ethics",
    r"Corporate\s+(?:&|and)\s+Economic\s+Laws",
    r"Corporate\s+(?:&|and)\s+Other\s+Laws",
    r"Direct\s+Tax\s+Laws\s+(?:&|and)\s+International\s+Taxation",
    r"Direct\s+Tax\s+Laws",
    r"Direct\s+Tax(?:ation)?",
    r"Indirect\s+Tax\s+Laws",
    r"Indirect\s+Tax(?:ation)?",
    r"Integrated\s+Business\s+Solutions",
    r"Strategic\s+Cost\s+Management\s+(?:&|and)\s+Performance\s+Evaluation",
    r"Strategic\s+Cost\s+Management",
    # CA Intermediate
    r"Advanced\s+Accounting",
    r"Accounting",
    r"Cost\s+(?:&|and)\s+Management\s+Accounting",
    r"Taxation",
    r"Auditing\s+(?:&|and)\s+Ethics",
    r"Auditing\s+(?:&|and)\s+Assurance",
    r"Financial\s+Management\s+(?:&|and)\s+Strategic\s+Management",
    r"Enterprise\s+Information\s+Systems\s+(?:&|and)\s+Strategic\s+Management",
    # CA Foundation
    r"Principles\s+(?:&|and)\s+Practice\s+of\s+Accounting",
    r"Business\s+Laws",
    r"Business\s+Mathematics(?:\s*,\s*Logical\s+Reasoning)?\s+(?:&|and)\s+Statistics",
    r"Quantitative\s+Aptitude",
    r"Business\s+Economics",
    r"Business\s+Commercial\s+Knowledge",
]

DOCUMENT_METADATA_PATTERNS = [
    r"(?i)^[ \t]*(?:PART|SECTION)\s+[A-Z0-9IVX]+[-–—\s:]+.*$",
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
    r"(?i)^[ \t]*(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s*[,–—\-]?\s*\d{4}(?:\s+(?:EXAMINATION|EXAMS?))?\s*$",
    r"(?i)^[ \t]*\d{4}\s+(?:EXAMINATION|EXAMS?)\s*$",
    r"(?i)^[ \t]*PAPER\s*[-–—:]\s*\d+[\s\-–—:]*.*$",
    r"(?i)^[ \t]*(?:PAPER\s*[-–—:]*\s*\d+[\s\-–—:]*)?(?:" + "|".join(KNOWN_SUBJECT_PATTERNS) + r")(?:\s*\([A-Za-z0-9]+\))?[\s.:\-–—]*$",
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
    r"^[ \t]*([1-9])\.([1-9]|1[0-5])[ \t]*$",                                                                    # 1.1, 1.2, 2.1 (Case study decimal questions 1.1 to 9.15)
    r"(?i)^[ \t]*Question\s+(?:No\.\s*)?(\d+)(?:[ \t]*\([^)]+\))*(?!\s+(?:to|-|–|—)\s+(?:Question|Q\.?\s*)?\d+)", # Question 1, Question 1(a), Question 1(a)(i)
    r"(?i)^[ \t]*Q\.?\s?(\d+)(?:[ \t]*\([^)]+\))*(?!\s+(?:to|-|–|—)\s+(?:Q\.?\s*)?\d+)",                         # Q1, Q. 1, Q1(a)
    r"^[ \t]*(\d{1,2})[.)](?!\d)(?:[ \t]*\([^)]+\))*(?!\s+(?:to|-|–|—)\s+(?:Q\.?\s*)?\d+)",                      # 1. or 1) or 1.(a) (max 99)
    r"^[ \t]*\(([a-zA-Z])\)",                                                                                    # (a)
    r"^[ \t]*\(([ivxIVX]+)\)(?!\s*e\.)",                                                                         # (i), (ii), (iv)
    r"^[ \t]*\d{1,2}\s*\(([a-z])\)",                                                                             # 1(a)
    r"^[ \t]*([a-z])\s*[.)](?!\s*e\.)(?![a-zA-Z])",                                                             # a. or a)
]

# Answer Header Patterns
# Matches: Answer to Question 1, Ans. 1, Solution 1, 1.1, or just 1. in Answer section
ANSWER_HEADER_PATTERNS = [
    r"^[ \t]*([1-9])\.([1-9]|1[0-5])[ \t]*$",                                         # 1.1, 1.2, 2.1
    r"(?i)^[ \t]*Answer\s+(?:to\s+)?(?:Question\s+)?(?:No\.\s*)?(\d+)(?:[ \t]*\(([a-z])\))?", # Answer to Question 1(a)
    r"(?i)^[ \t]*Ans\.?\s*(\d+)(?:[ \t]*\(([a-z])\))?",                                       # Ans. 1(a)
    r"(?i)^[ \t]*Solution\s*(\d+)(?:[ \t]*\(([a-z])\))?",                                     # Solution 1(a)
    r"(?i)^[ \t]*(?:Question|Q\.?)\s*(?:No\.\s*)?(\d+)(?:[ \t]*\(([a-z])\))?",                # Question 1 or Q1
    r"^[ \t]*(\d{1,2})[.)](?!\d)(?:[ \t]*\(([a-z])\))?",                                     # 1. or 1.(a)
    r"^[ \t]*(\d{1,2})[.)]?[ \t]*\(([a-zA-Z])\)",                                            # 14(a) or 14.(a)
    r"^[ \t]*(\d{1,2})[.)]?[ \t]*\(([ivxIVX]+)\)",                                           # 6(i) or 6.(i)
    r"^[ \t]*\(([a-zA-Z])\)",                                                                # (a)
    r"^[ \t]*\(([ivxIVX]+)\)(?!\s*e\.)",                                                     # (i), (ii), (iv)
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
        case_study_keywords=["CASE SCENARIO", "CASE STUDY", "INTEGRATED CASE SCENARIO", "CASE SCENARIOS"],
        instruction_priority=INSTRUCTION_PRIORITY,
        marks_patterns=COMPILED_MARKS_PATTERNS,
        marks_exclusion_patterns=COMPILED_MARKS_EXCLUSION_PATTERNS,
        semantic_score_threshold=DEFAULT_SEMANTIC_SCORE_THRESHOLD,
        question_start_patterns=COMPILED_QUESTION_START_PATTERNS
    )
