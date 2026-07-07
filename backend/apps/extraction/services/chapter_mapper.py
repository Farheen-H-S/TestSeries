import re
import string
from typing import Optional, Sequence, TypedDict, Pattern
from apps.syllabus.models import Chapter, Subject, ChapterKeyword

# Precompile regexes at module level for efficiency
RE_PUNCTUATION = re.compile(f"[{re.escape(string.punctuation)}]")
RE_SPACES = re.compile(r"\s+")

# Logic Constants
MINIMUM_MAPPING_SCORE = 1

class PreparedChapter(TypedDict):
    """
    Structure representing a chapter and its pre-normalized keyword patterns.
    """
    chapter: Chapter
    patterns: Sequence[Pattern[str]]

def normalize_text(text: str) -> str:
    """
    Normalize text for deterministic rule-based matching.
    
    Normalization Rules:
    1. Lowercase conversion.
    2. Punctuation removal (replaced with space).
    3. Collapse multiple spaces and trim.
    """
    if not text:
        return ""
    
    text = text.lower()
    text = RE_PUNCTUATION.sub(" ", text)
    text = RE_SPACES.sub(" ", text).strip()
    
    return text

def get_prepared_chapters(subject: Subject) -> Sequence[PreparedChapter]:
    """
    Pre-loads and normalizes chapter keyword data for a subject once.
    
    This avoids N+1 database queries and redundant normalization during extraction.
    """
    chapters = Chapter.objects.filter(subject=subject).select_related("keyword_record")
    
    prepared_chapters: list[PreparedChapter] = []
    for chapter in chapters:
        try:
            kw_record = chapter.keyword_record
            if not kw_record or not kw_record.keywords:
                continue
        except ChapterKeyword.DoesNotExist:
            continue
            
        raw_keywords = kw_record.keywords.splitlines()
        patterns: list[Pattern[str]] = []
        unique_kws = set()
        
        for kw in raw_keywords:
            n_kw = normalize_text(kw)
            if n_kw and n_kw not in unique_kws:
                unique_kws.add(n_kw)
                
                # 1. Escape the keyword to treat user-entered text literally (no regex syntax allowed).
                # 2. Replace escaped spaces with \s+ to handle OCR variations in spacing robustly.
                escaped_kw = re.escape(n_kw).replace(r"\ ", r"\s+").replace(" ", r"\s+")
                
                # Whole-word/phrase boundary matching
                patterns.append(re.compile(rf"\b{escaped_kw}\b"))
        
        if patterns:
            prepared_chapters.append({
                "chapter": chapter,
                "patterns": patterns
            })
            
    return prepared_chapters

def map_question_to_chapter(
    question_text: str, 
    prepared_chapters: Sequence[PreparedChapter]
) -> Optional[Chapter]:
    """
    Deterministically map a question to a chapter based on keyword scores.
    
    Rules:
    - Scoring: Every unique keyword pattern found within word boundaries adds 1 point.
    - Ties: If multiple chapters share the highest score, returns None to avoid ambiguity.
    - Confidence: Highest score must be >= MINIMUM_MAPPING_SCORE.
    
    Returns:
    - Chapter: Exactly one chapter achieved the highest score (min 1).
    - None: Any of the following:
        - Question text is empty after normalization.
        - Prepared chapter list is empty.
        - No keywords matched for any chapter (max_score < MINIMUM_MAPPING_SCORE).
        - Multiple chapters tied for the highest score.
    
    TODO: Support keyword weights in PreparedChapter without changing function signature.
    """
    normalized_q = normalize_text(question_text)
    if not normalized_q or not prepared_chapters:
        return None
        
    best_chapter: Optional[Chapter] = None
    max_score: int = 0
    is_tie: bool = False
    
    for item in prepared_chapters:
        score: int = 0
        for pattern in item["patterns"]:
            if pattern.search(normalized_q):
                score += 1
        
        if score > max_score:
            max_score = score
            best_chapter = item["chapter"]
            is_tie = False
        elif score == max_score and score >= MINIMUM_MAPPING_SCORE:
            # Equal highest scores intentionally return None to avoid 
            # assigning an incorrect chapter when ambiguity exists.
            is_tie = True
            
    if max_score >= MINIMUM_MAPPING_SCORE and not is_tie:
        return best_chapter
        
    return None
