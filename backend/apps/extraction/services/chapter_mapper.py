import re
import string
import logging
from typing import Optional, List, TypedDict, Pattern
from apps.syllabus.models import Chapter, Subject, ChapterKeyword

# Initialize logger
logger = logging.getLogger(__name__)

# Precompile regexes at module level for efficiency
RE_PUNCTUATION = re.compile(f'[{re.escape(string.punctuation)}]')
RE_SPACES = re.compile(r'\s+')

class PreparedChapter(TypedDict):
    """
    Structure representing a chapter and its pre-normalized keyword patterns.
    """
    chapter: Chapter
    patterns: List[Pattern[str]]

def normalize_text(text: str) -> str:
    """
    Normalize text for deterministic rule-based matching.
    
    Normalization Rules:
    1. Lowercase conversion: All text is converted to lower case.
    2. Punctuation removal: Characters like !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ are replaced with spaces.
    3. Whitespace optimization: Multiple spaces are collapsed into one, and leading/trailing spaces are trimmed.
    
    Example:
    "Cash-Flow: Statement?" -> "cash flow statement"
    """
    if not text:
        return ""
    
    # 1. Lowercase
    text = text.lower()
    
    # 2. Remove punctuation (replace with space to prevent merging words, e.g., "Cash-Flow")
    text = RE_PUNCTUATION.sub(' ', text)
    
    # 3. Collapse multiple spaces and trim
    text = RE_SPACES.sub(' ', text).strip()
    
    return text

def get_prepared_chapters(subject: Subject) -> List[PreparedChapter]:
    """
    Pre-loads and normalizes chapter keyword data for a subject once.
    
    This optimization avoids N+1 database queries by using select_related('keyword_record')
    and ensures that keywords are only normalized and compiled into regexes once per document.
    
    Processing Steps:
    1. Fetch all chapters for the subject with their OneToOne keyword record.
    2. Split keywords (one per line).
    3. Normalize each keyword and convert it into a whole-word regex pattern (\b).
       - This ensures 'as' matches 'as' but not 'basic'.
       - Multi-word keywords like 'cash flow' match 'cash flow statement' but not 'cashflow'.
    """
    chapters = Chapter.objects.filter(subject=subject).select_related('keyword_record')
    
    prepared_chapters: List[PreparedChapter] = []
    for chapter in chapters:
        try:
            kw_record = chapter.keyword_record
            if not kw_record or not kw_record.keywords:
                continue
        except ChapterKeyword.DoesNotExist:
            continue
            
        raw_keywords = kw_record.keywords.splitlines()
        patterns: List[Pattern[str]] = []
        unique_kws = set()
        
        for kw in raw_keywords:
            n_kw = normalize_text(kw)
            if n_kw and n_kw not in unique_kws:
                unique_kws.add(n_kw)
                # Whole-word/phrase boundary matching
                patterns.append(re.compile(rf'\b{re.escape(n_kw)}\b'))
        
        if patterns:
            prepared_chapters.append({
                'chapter': chapter,
                'patterns': patterns
            })
            
    return prepared_chapters

def map_question_to_chapter(
    question_text: str, 
    prepared_chapters: List[PreparedChapter]
) -> Optional[Chapter]:
    """
    Deterministically map a question to a chapter based on keyword scores.
    
    Logic & Constraints:
    - Normalization: The question undergoes the same normalization rules as keywords.
    - Scoring: Every unique keyword pattern found within the question adds 1 point to the score.
    - Tie Behavior: If multiple chapters share the same highest score, returns None to avoid bias.
    - Confidence: The highest score must be > 0.
    - Determinism: No AI, fuzzy matching, or semantic search is used.
    
    Examples:
    - Keyword "cash flow" matches "cash flow statement" but not "cashflow".
    - Keyword "as" matches "as" but not "basic".
    
    TODO: Support keyword weights in the PreparedChapter structure to allow 
    fine-grained scoring without changing the external function signature.
    """
    normalized_q = normalize_text(question_text)
    if not normalized_q or not prepared_chapters:
        return None
        
    best_chapter: Optional[Chapter] = None
    max_score: int = 0
    is_tie: bool = False
    
    for item in prepared_chapters:
        score: int = 0
        for pattern in item['patterns']:
            if pattern.search(normalized_q):
                score += 1
        
        if score > max_score:
            max_score = score
            best_chapter = item['chapter']
            is_tie = False
        elif score == max_score and score > 0:
            # Equal highest scores intentionally return None to avoid 
            # assigning an incorrect chapter when ambiguity exists.
            is_tie = True
            
    if max_score > 0 and not is_tie:
        return best_chapter
        
    return None
