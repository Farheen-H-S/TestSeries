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
            var_name = re.sub(r'ing\b', '(?:ing|s)?', n_name)
            escaped_name = re.escape(n_name).replace(r"\ ", r"\s+").replace(" ", r"\s+")
            patterns_with_weights.append((re.compile(rf"\b{escaped_name}\b", re.IGNORECASE), 5))
            if var_name != n_name:
                escaped_var = var_name.replace(" ", r"\s+")
                patterns_with_weights.append((re.compile(rf"\b{escaped_var}\b", re.IGNORECASE), 5))
            unique_patterns.add(n_name)
            
        # 2. Code/number designation prefix like "Ind AS 110", "Ind AS 1", "AS 16", "Chapter 3" (weight=1)
        code_match = re.search(r'(?i)\b(Ind\s*AS\s*\d+|AS\s*\d+|Chapter\s*\d+)\b', name)
        if code_match:
            code_str = normalize_text(code_match.group(1))
            if code_str and code_str not in unique_patterns:
                escaped_code = re.escape(code_str).replace(r"\ ", r"\s+").replace(" ", r"\s+")
                patterns_with_weights.append((re.compile(rf"\b{escaped_code}\b", re.IGNORECASE), 1))
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
    Uses longest-match tie-breaking for nested chapter names (e.g. 'Interest Rate Risk Management' vs 'Risk Management').
    """
    normalized_q = normalize_text(question_text)
    if not normalized_q or not prepared_chapters:
        return None
        
    best_chapter: Optional[Chapter] = None
    max_score: int = 0
    best_match_len: int = 0
    is_tie: bool = False
    
    for item in prepared_chapters:
        score: int = 0
        current_max_len: int = 0
        for pattern, weight in item["patterns_with_weights"]:
            match = pattern.search(normalized_q)
            if match:
                score += weight
                current_max_len = max(current_max_len, len(match.group(0)))
        
        if score > max_score:
            max_score = score
            best_chapter = item["chapter"]
            best_match_len = current_max_len
            is_tie = False
        elif score == max_score and score >= MINIMUM_MAPPING_SCORE:
            if current_max_len > best_match_len:
                # Longer, more specific chapter name match breaks the tie
                best_chapter = item["chapter"]
                best_match_len = current_max_len
                is_tie = False
    if max_score >= MINIMUM_MAPPING_SCORE and not is_tie:
        return best_chapter
        
    return None

CHAPTER_HEADING_LINE_PATTERNS = [
    re.compile(r'(?i)^[ \t]*(?:Ind\s*AS|AS|SA|CARO|Chapter|Section|Module|Paper|Topic)\s*\d+[\s\-–—:]', re.IGNORECASE),
    re.compile(r'(?i)^[ \t]*(?:Ind\s*AS|AS|SA|CARO)\s*\d+\b', re.IGNORECASE),
    re.compile(r'(?i)^[ \t]*Chapter\s*[-–—:]?\s*\d+\b', re.IGNORECASE),
]

def find_chapter_for_question_context(
    lines_before: Sequence[str],
    prepared_chapters: Sequence[dict]
) -> Optional[Chapter]:
    """
    Identifies if a true chapter heading explicitly precedes a question block.
    If no valid heading exists (e.g. for Case Scenario questions or un-headed questions), returns None.
    """
    if not prepared_chapters or not lines_before:
        return None

    for line in reversed(lines_before[-6:]):
        line_clean = line.strip()
        if not line_clean:
            continue
        # Exclude MCQ options or scenario prompt sentences
        if re.match(r'(?i)^\s*(?:\([a-eA-E]\)|Option\b|Ans\.?|Choice|Key)', line_clean):
            continue
        if re.search(r'(?i)\b(?:choose|answer to Questions?|Based on the facts|given above|Read the following|Answer all|Answer any)\b', line_clean):
            continue
        
        is_explicit_heading = any(pat.match(line_clean) for pat in CHAPTER_HEADING_LINE_PATTERNS)
        if is_explicit_heading:
            ch = map_question_to_chapter(line_clean, prepared_chapters)
            if ch:
                return ch
            # Explicit standard header not present in current syllabus -> None
            return None
        
        # Standalone short chapter title line
        if len(line_clean) < 80 and not line_clean.endswith(('.', '?', '!', ';')):
            ch = map_question_to_chapter(line_clean, prepared_chapters)
            if ch and ch.chapter_name and (line_clean.lower() in ch.chapter_name.lower() or ch.chapter_name.lower() in line_clean.lower()):
                return ch

    return None
