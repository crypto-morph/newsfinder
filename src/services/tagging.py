import re
from typing import List, Dict, Any
from src.analysis.llm_client import OllamaClient

STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "their",
    "your", "about", "across", "through", "over", "under", "health",
    "wellness", "services", "service", "business",
}

def extract_keywords(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return [token for token in tokens if token not in STOPWORDS]

def match_goals(text: str, goals: List[str]) -> List[str]:
    matches: List[str] = []
    for goal in goals:
        keywords = extract_keywords(goal)
        if any(keyword in text for keyword in keywords):
            matches.append(goal)
    return matches

def derive_topic_tags(article: Dict[str, Any], keyword_matches: List[str]) -> List[str]:
    stored_tags = article.get("topic_tags")
    if isinstance(stored_tags, list) and stored_tags:
        return stored_tags
    if keyword_matches:
        return keyword_matches

    title = article.get("title", "")
    summary = article.get("summary_text", "")
    keywords = extract_keywords(f"{title} {summary}")
    return keywords[:4]

def generate_tag_rationale(
    ollama: OllamaClient,
    article: Dict[str, Any],
    topic_tags: List[str],
    entity_tags: List[str],
) -> str:
    prompt = f"""
    You are explaining why article tags were chosen. Provide a short explanation
    (2-3 sentences) tying tags to the article summary.

    Article Title: {article.get('title', '')}
    Article Summary: {article.get('summary_text', '')}
    Topic Tags: {', '.join(topic_tags)}
    Entity Tags: {', '.join(entity_tags)}
    """

    response = ollama.generate_json(
        prompt + "\nReturn JSON with field: rationale"
    )
    if not response:
        return ""
    return str(response.get("rationale", "")).strip()
