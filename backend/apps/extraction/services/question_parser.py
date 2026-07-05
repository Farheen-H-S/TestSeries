import re
from typing import List, Dict, Any

# Matches headers like "1.", "1)", "Q1", "Q.1", "Question 1"
# Captures the question number in group 1
RE_QUESTION_START = re.compile(
    r'^\s*(?:Question\s+|Q\.?\s?|)(\d+)[.)]?\s+',
    re.MULTILINE | re.IGNORECASE
)

def parse_questions(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse extracted page text into individual questions based on numbering patterns.
    
    Args:
        pages: List of dictionaries containing "page_number" and "text".
        
    Returns:
        List of dictionaries with:
        - question_number: The detected number (str)
        - question_text: The full text of the question (str)
        - source_page: The page number where the question started (int)
    """
    all_questions = []
    current_q = None
    
    for page in pages:
        text = page.get("text", "")
        page_num = page.get("page_number")
        
        matches = list(RE_QUESTION_START.finditer(text))
        
        if not matches:
            # If no matches on this page, the whole page belongs to the current question
            if current_q:
                # Add a newline then the page text
                current_q["question_text"] += "\n" + text.strip()
            continue
            
        for i, match in enumerate(matches):
            if i == 0:
                # Text before the first match on this page belongs to the previous question
                pre_text = text[:match.start()].strip()
                if pre_text and current_q:
                    current_q["question_text"] += "\n" + pre_text
            
            # Start a new question
            # We explicitly exclude the header (match.group(0)) from the text
            # normalizing question_number to remove leading zeros
            current_q = {
                "question_number": str(int(match.group(1))),
                "question_text": "",
                "source_page": page_num
            }
            
            # Append the rest of the text until the next match or end of page
            next_start = matches[i+1].start() if i + 1 < len(matches) else len(text)
            content = text[match.end():next_start].strip()
            if content:
                current_q["question_text"] = content
                
            all_questions.append(current_q)
            
    # Final cleanup: trim whitespace for all questions
    for q in all_questions:
        q["question_text"] = q["question_text"].strip()
        
    return all_questions
