import re

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

# Question Header Patterns
# Matches: Question 1, Q1, Q.1, 1., 1(a), (a), (i)
QUESTION_HEADER_PATTERNS = [
    r"(?i)^Question\s+(?:No\.\s*)?(\d+)",          # Question 1, Question No. 1
    r"(?i)^Q\.?\s?(\d+)",                          # Q1, Q. 1
    r"^(\d+)[.)]",                                 # 1. or 1)
    r"^\(([a-zA-Z])\)",                            # (a)
    r"^\(([ivxIVX]+)\)",                           # (i), (ii), (iv)
    r"^\d+\s*\(([a-z])\)",                         # 1(a)
    r"^([a-z])\s*[.)]",                            # a. or a)
]

# Answer Header Patterns
# Matches: Answer to Question 1, Ans. 1, Solution 1, or just 1. in Answer section
ANSWER_HEADER_PATTERNS = [
    r"(?i)^Answer\s+(?:to\s+)?(?:Question\s+)?(?:No\.\s*)?(\d+)(?:\(([a-z])\))?", # Answer to Question 1(a)
    r"(?i)^Ans\.?\s*(\d+)(?:\(([a-z])\))?",                                       # Ans. 1(a)
    r"(?i)^Solution\s*(\d+)(?:\(([a-z])\))?",                                     # Solution 1(a)
    r"^(\d+)[.)](?:\s*\(([a-z])\))?",                                             # 1. or 1.(a)
]

# Marks Extraction Patterns
MARKS_PATTERNS = [
    r"\(\s*(\d+)\s*[Mm]arks?\s*\)",           # (5 Marks)
    r"\[\s*(\d+)\s*[Mm]arks?\s*\]",           # [5 Marks]
    r"\(\s*(\d+)\s*\)",                       # (5)
    r"\[\s*(\d+)\s*\]",                       # [5]
    r"\b(\d+)\s*[Mm]\b"                       # 5M or 5 M
]

# Marks Exclusion Patterns (To avoid False Positives)
MARKS_EXCLUSION_PATTERNS = [
    r"\b(20\d{2}|19\d{2})\b",                 # Years
    r"\b(?:Ind\s+AS|AS|SA|CARO)\s+\d+\b",     # Standards
    r"\b(?:Sec|Section)\.?\s+\d+[A-Z]*\b",     # Sections
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
        "CALCULATE", "COMPUTE", "PREPARE", "JOURNALIZE", "LEDGER", 
        "BALANCE SHEET", "PROFIT AND LOSS", "RECONCILE"
    ],
    "THEORY": [
        "EXPLAIN", "DISCUSS", "DEFINE", "STATE", "LIST", "DISTINGUISH", 
        "DIFFERENTIATE", "COMPARE"
    ],
    "CASE_STUDY": [
        "ABC LTD", "PQR LTD", "XYZ LTD", "M/S", "MR.", "MRS.", 
        "FOLLOWING INFORMATION", "BASED ON THE ABOVE", "READ THE FOLLOWING"
    ],
    "OBJECTIVE": [
        "TRUE OR FALSE", "MULTIPLE CHOICE", "MCQ", "CHOOSE THE CORRECT"
    ]
}
