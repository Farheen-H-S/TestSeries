import re
import string
from typing import Optional, List, Dict, Any
from apps.syllabus.models import Chapter, Subject, ChapterKeyword

# Precompile regexes at module level for efficiency
RE_PUNCTUATION = re.compile(f'[{re.escape(string.punctuation)}]')
RE_SPACES = re.compile(r'\s+')

def normalize_text(text: str) -> str:
    """
    Normalize text for deterministic matching.
    
    Rules:
    - Lowercase conversion
    - Replace punctuation with spaces
    - Trim whitespace
    - Collapse multiple spaces into one
    """
    if not text:
        return ""
    
    # 1. Lowercase
    text = text.lower()
    
    # 2. Remove punctuation (replace with space to prevent merging words)
    text = RE_PUNCTUATION.sub(' ', text)
    
    # 3. Collapse multiple spaces and trim
    text = RE_SPACES.sub(' ', text).strip()
    
    return text

def get_prepared_chapters(subject: Subject) -> List[Dict[str, Any]]:
    """
    Pre-loads and normalizes chapter keyword data for a subject once.
    This avoids N+1 database queries and redundant normalization.
    """
    # Fetch chapters and their unique keyword records in one go
    chapters = Chapter.objects.filter(subject=subject).select_related('keyword_record')
    
    prepared_data = []
    for chapter in chapters:
        try:
            # Access related object directly (OneToOneField)
            kw_record = chapter.keyword_record
            if not kw_record or not kw_record.keywords:
                continue
        except ChapterKeyword.DoesNotExist:
            # Handle missing keyword record gracefully
            continue
            
        raw_keywords = kw_record.keywords.splitlines()
        patterns = []
        unique_kws = set()
        
        for kw in raw_keywords:
            n_kw = normalize_text(kw)
            if n_kw and n_kw not in unique_kws:
                unique_kws.add(n_kw)
                # Precompile word-boundary regex for exact whole-word/phrase matching.
                # This ensures 'as' doesn't match 'basic'.
                patterns.append(re.compile(rf'\b{re.escape(n_kw)}\b'))
        
        if patterns:
            prepared_data.append({
                'chapter': chapter,
                'patterns': patterns
            })
            
    return prepared_data

def map_question_to_chapter(
    question_text: str, 
    subject: Subject,
    prepared_data: Optional[List[Dict[str, Any]]] = None
) -> Optional[Chapter]:
    """
    Deterministically map a question to a chapter based on keyword scores.
    
    Rules & Logic:
    - Normalization: Both question and keywords are normalized (lowercase, no punctuation).
    - Match Type: Deterministic whole-word boundary matching (regex \b).
    - Score Calculation: Number of unique keywords found in the question text.
    - Tie Behaviour: Returns None if multiple chapters share the highest score.
    - Confidence: Highest score must be > 0.
    
    Performance:
    - Use get_prepared_chapters() once per document to avoid N+1 queries.
    """
    normalized_q = normalize_text(question_text)
    if not normalized_q:
        return None
        
    # Use provided data or fetch on the fly (less efficient)
    data = prepared_data if prepared_data is not None else get_prepared_chapters(subject)
    
    best_chapter = None
    max_score = 0
    is_tie = False
    
    for item in data:
        score = 0
        for pattern in item['patterns']:
            # Whole-word / phrase matching
            if pattern.search(normalized_q):
                score += 1
        
        if score > max_score:
            max_score = score
            best_chapter = item['chapter']
            is_tie = False
        elif score == max_score and score > 0:
            is_tie = True
            
    if max_score > 0 and not is_tie:
        return best_chapter
        
    return None
