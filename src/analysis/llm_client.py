import requests
import logging
from typing import List, Dict, Any
import json

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "LiquidAI/LFM2.5-1.2B-Instruct",
        embedding_model: str = "nomic-embed-text",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embedding_model = embedding_model

    def check_connection(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def warmup(self) -> bool:
        """
        Send a lightweight request to force the model to load into memory.
        Returns True if successful.
        """
        logger.info(f"Warming up Ollama model: {self.model}")
        try:
            # Simple generation request
            self.generate_json('{"test": "warmup"}', timeout=60)
            # Also warmup embedding model if possible (by generating one embedding)
            self.generate_embedding("warmup")
            return True
        except Exception as e:
            logger.error(f"Warmup failed: {e}")
            return False

    def generate_embedding(self, text: str) -> List[float]:
        """Generate vector embedding for a given text."""
        if not text:
            return []

        url = f"{self.base_url}/api/embeddings"
        payload = {"model": self.embedding_model, "prompt": text}
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("embedding", [])
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []

    def analyze_article(self, text: str, context: str = "") -> Dict[str, Any]:
        """
        Analyze article text using the LLM to get summary, relevance, and impact.
        Returns a JSON object.
        """
        clipped_text = text[:4000]
        prompt = f"""
        You are a business intelligence analyst.

        STRATEGIC CONTEXT (Primary Company & Competitors):
        {context}

        ARTICLE TEXT:
        {clipped_text}

        TASK:
        Analyze the article above and provide a JSON response with the following fields:
        - summary: A concise 2-3 sentence summary.
        - relevance_score: Integer 1-10 (how relevant is this to the PRIMARY company's goals?).
        - relevance_reasoning: A short sentence explaining WHY this score was given.
        - impact_score: Integer 1-10 (how big is the potential impact on the market or competitors?).
        - key_entities: A list of important companies, people, or technologies mentioned.

        RESPONSE FORMAT:
        Return ONLY valid JSON. Do not include markdown formatting or explanations.
        """

        response = self.generate_json(prompt)
        if not response:
            logger.error("LLM returned empty analysis response")
            return {
                "summary": "LLM analysis unavailable",
                "relevance_score": 0,
                "relevance_reasoning": "Analysis failed",
                "impact_score": 0,
                "key_entities": [],
            }

        return {
            "summary": response.get("summary", "No summary generated"),
            "relevance_score": response.get("relevance_score", 0),
            "relevance_reasoning": response.get("relevance_reasoning", ""),
            "impact_score": response.get("impact_score", 0),
            "key_entities": response.get("key_entities", []),
        }

    def extract_topics(self, text: str, max_topics: int = 5) -> List[str]:
        """Extract concise topic tags for an article."""
        clipped_text = text[:3500]
        prompt = f"""
        You are labeling news articles. Return ONLY JSON with a single field:
        - topics: list[str] of 3-6 short, meaningful topic tags (2-4 words each).
        Avoid generic words, focus on the main themes.

        ARTICLE TEXT:
        {clipped_text}
        """

        response = self.generate_json(prompt)
        topics = response.get("topics", []) if response else []
        if not isinstance(topics, list):
            return []
        cleaned = [str(topic).strip() for topic in topics if str(topic).strip()]
        return cleaned[:max_topics]

    def generate_json(self, prompt: str, timeout: int = 120) -> Dict[str, Any]:
        """Helper to request a JSON-formatted response from Ollama."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            result_text = response.json().get("response", "")
            if not result_text:
                return {}
            return json.loads(result_text)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON response from Ollama")
            return {}
        except Exception as exc:
            logger.error("Error calling Ollama JSON endpoint: %s", exc)
            return {}
