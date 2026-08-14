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
    
    Extracts patterns from chapter.chapter_name (full name, code/number prefix, topic portion)
    and any optional ChapterKeyword records.
    """
    if not subject:
        return []

    chapters = Chapter.objects.filter(subject=subject).select_related("keyword_record")
    prepared_chapters: list[dict] = []
    
    for chapter in chapters:
        patterns_with_weights: list[tuple[Pattern[str], int]] = []
        unique_patterns = set()
        
        name = (chapter.chapter_name or "").strip()
        n_name = normalize_text(name)
        
        # 1. Full chapter name pattern (weight=5)
        if n_name:
            escaped_name = re.escape(n_name).replace(r"\ ", r"\s+").replace(" ", r"\s+")
            patterns_with_weights.append((re.compile(rf"\b{escaped_name}\b", re.IGNORECASE), 5))
            unique_patterns.add(n_name)
            
        # 2. Code/number designation prefix like "Ind AS 110", "Ind AS 1", "AS 16", "Chapter 3" (weight=3)
        code_match = re.search(r'(?i)\b(Ind\s*AS\s*\d+|AS\s*\d+|Chapter\s*\d+)\b', name)
        if code_match:
            code_str = normalize_text(code_match.group(1))
            if code_str and code_str not in unique_patterns:
                escaped_code = re.escape(code_str).replace(r"\ ", r"\s+").replace(" ", r"\s+")
                patterns_with_weights.append((re.compile(rf"\b{escaped_code}\b", re.IGNORECASE), 3))
                unique_patterns.add(code_str)

        # 3. Topic title after colon if present (e.g. "Consolidated Financial Statements") (weight=2)
        if ":" in name:
            topic_part = name.split(":", 1)[1].strip()
            n_topic = normalize_text(topic_part)
            if n_topic and len(n_topic) >= 4 and n_topic not in unique_patterns:
                escaped_topic = re.escape(n_topic).replace(r"\ ", r"\s+").replace(" ", r"\s+")
                patterns_with_weights.append((re.compile(rf"\b{escaped_topic}\b", re.IGNORECASE), 2))
                unique_patterns.add(n_topic)
                
        # 4. Optional keywords from ChapterKeyword record (weight=1)
        try:
            kw_record = getattr(chapter, "keyword_record", None)
            if kw_record and kw_record.keywords:
                raw_keywords = kw_record.keywords.splitlines()
                for kw in raw_keywords:
                    n_kw = normalize_text(kw)
                    if n_kw and n_kw not in unique_patterns:
                        unique_patterns.add(n_kw)
                        escaped_kw = re.escape(n_kw).replace(r"\ ", r"\s+").replace(" ", r"\s+")
                        patterns_with_weights.append((re.compile(rf"\b{escaped_kw}\b", re.IGNORECASE), 1))
        except Exception:
            pass

        if patterns_with_weights:
            prepared_chapters.append({
                "chapter": chapter,
                "patterns_with_weights": patterns_with_weights
            })
            
    return prepared_chapters

def map_question_to_chapter(
    question_text: str, 
    prepared_chapters: Sequence[dict]
) -> Optional[Chapter]:
    """
    Deterministically map text to a chapter based on weighted pattern scores.
    """
    normalized_q = normalize_text(question_text)
    if not normalized_q or not prepared_chapters:
        return None
        
    best_chapter: Optional[Chapter] = None
    max_score: int = 0
    is_tie: bool = False
    
    for item in prepared_chapters:
        score: int = 0
        for pattern, weight in item["patterns_with_weights"]:
            if pattern.search(normalized_q):
                score += weight
        
        if score > max_score:
            max_score = score
            best_chapter = item["chapter"]
            is_tie = False
        elif score == max_score and score >= MINIMUM_MAPPING_SCORE:
            is_tie = True
            
    if max_score >= MINIMUM_MAPPING_SCORE and not is_tie:
        return best_chapter
        
    return None
