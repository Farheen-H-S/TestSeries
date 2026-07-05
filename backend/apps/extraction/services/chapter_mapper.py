import re
import string
from typing import Optional
from apps.syllabus.models import Chapter, Subject, ChapterKeyword

def normalize_text(text: str) -> str:
    """
    Normalize text for deterministic matching:
    - Lowercase conversion
    - Trim whitespace
    - Collapse multiple spaces into one
    - Remove punctuation
    """
    if not text:
        return ""
    
    # 1. Lowercase
    text = text.lower()
    
    # 2. Remove punctuation
    # Create a regex pattern to match any punctuation character
    punc_pattern = re.compile(f'[{re.escape(string.punctuation)}]')
    text = punc_pattern.sub(' ', text)
    
    # 3. Collapse multiple spaces and trim
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def map_question_to_chapter(question_text: str, subject: Subject) -> Optional[Chapter]:
    """
    Deterministically map a question to a chapter based on keyword scores.
    
    Score = count of unique normalized keywords present in the normalized question text.
    
    Rules:
    - Highest score wins (must be > 0).
    - If there is a tie for the highest score, returns None.
    - If no chapters have a score > 0, returns None.
    """
    normalized_q = normalize_text(question_text)
    if not normalized_q:
        return None
        
    # Get all chapters for this subject
    # We prefetch keyword_records to minimize database hits in the loop
    chapters = Chapter.objects.filter(subject=subject).prefetch_related('keyword_records')
    
    best_chapter = None
    max_score = 0
    is_tie = False
    
    for chapter in chapters:
        # One keyword record per chapter as per constraint
        kw_record = chapter.keyword_records.first()
        if not kw_record or not kw_record.keywords:
            continue
            
        # Split keywords by line and normalize them
        # Note: We use a set of unique normalized keywords
        raw_keywords = kw_record.keywords.splitlines()
        normalized_keywords = set()
        for kw in raw_keywords:
            n_kw = normalize_text(kw)
            if n_kw:
                normalized_keywords.add(n_kw)
        
        # Calculate matching score
        score = 0
        for kw in normalized_keywords:
            # Deterministic check: Is the keyword part of the question text?
            if kw in normalized_q:
                score += 1
        
        if score > max_score:
            max_score = score
            best_chapter = chapter
            is_tie = False
        elif score == max_score and score > 0:
            is_tie = True
            
    if max_score > 0 and not is_tie:
        return best_chapter
        
    return None
