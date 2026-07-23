"""
Unified LLM client supporting Ollama (local HTTP) and Kiro ACP (persistent subprocess).
"""
import requests
import logging
from typing import List, Dict, Any
import json

from .acp_client import KiroCLIClient

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting Ollama and Kiro ACP."""

    @staticmethod
    def create(provider: str = "ollama", **kwargs):
        """Factory method to create appropriate LLM client."""
        if provider == "kiro":
            return KiroClient(**kwargs)
        return OllamaClient(**kwargs)


class KiroClient:
    """
    Kiro CLI-based LLM client using ACP (Agent Client Protocol).

    Maintains a persistent connection to kiro-cli acp — one subprocess handles
    all prompts for the lifetime of the client. Much faster than spawning
    per-call.
    """

    def __init__(
        self,
        model: str = None,
        effort: str = "low",
        embedding_model: str = "nomic-embed-text",
        **kwargs,
    ):
        self.embedding_model = embedding_model
        self.ollama_url = kwargs.get("base_url", "http://localhost:11434")

        self._cli = KiroCLIClient(
            effort=effort,
            agent="analyzer",
            model=model,
        )

    def check_connection(self) -> bool:
        """Check if kiro-cli is available."""
        return self._cli.check_connection()

    def warmup(self) -> bool:
        """No persistent process to warm up."""
        return self.check_connection()

    def shutdown(self) -> None:
        """No persistent process to stop."""
        pass

    def generate_embedding(self, text: str) -> List[float]:
        """Use Ollama for embeddings (ACP/Kiro doesn't support this)."""
        if not text:
            return []
        url = f"{self.ollama_url}/api/embeddings"
        payload = {"model": self.embedding_model, "prompt": text}
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as exc:
            logger.error("Embedding error: %s", exc)
            return []

    def generate_json(self, prompt: str, timeout: int = 300) -> Dict[str, Any]:
        """Send a prompt expecting a JSON response via kiro-cli."""
        return self._cli.prompt_json(prompt, timeout=timeout)

    def generate_text(self, prompt: str, timeout: int = 300) -> str:
        """Send a prompt for text generation via kiro-cli."""
        return self._cli.prompt(prompt, timeout=timeout)

    def extract_topics(self, text: str, max_topics: int = 5) -> List[str]:
        """Extract concise topic tags for an article."""
        clipped_text = text[:3500]
        prompt = (
            "Return ONLY JSON with a single field:\n"
            '- topics: list[str] of 3-6 short, meaningful topic tags (2-4 words each).\n'
            "Avoid generic words, focus on the main themes.\n\n"
            f"ARTICLE TEXT:\n{clipped_text}"
        )
        response = self.generate_json(prompt)
        topics = response.get("topics", []) if response else []
        if not isinstance(topics, list):
            return []
        cleaned = [str(topic).strip() for topic in topics if str(topic).strip()]
        return cleaned[:max_topics]

    def analyze_article(self, text: str, context: str = "") -> Dict[str, Any]:
        """Analyze article text to get summary, relevance, and impact."""
        clipped_text = text[:4000]

        # Load prompt from yaml
        prompt_template = ""
        try:
            with open("prompts.yaml", "r") as f:
                import yaml
                data = yaml.safe_load(f)
                prompt_template = data.get("analysis_prompt", "")
        except Exception:
            pass

        if not prompt_template:
            prompt_template = (
                "You are a business intelligence analyst.\n"
                "SECTION 1: STRATEGIC CONTEXT: {context}\n"
                "SECTION 2: ARTICLE TEXT: {clipped_text}\n"
                "TASK: Return JSON with summary, relevance_score (1-10), "
                "relevance_reasoning, impact_score (1-10), key_entities."
            )

        prompt = prompt_template.format(context=context, clipped_text=clipped_text)
        response = self.generate_json(prompt, timeout=300)

        if not response:
            logger.error("ACP returned empty analysis response")
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


class OllamaClient:
    """Local Ollama HTTP API client."""

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
        """Send a lightweight request to force the model to load into memory."""
        logger.info(f"Warming up Ollama model: {self.model}")
        try:
            self.generate_json('{"test": "warmup"}', timeout=60)
            self.generate_embedding("warmup")
            return True
        except Exception as e:
            logger.error(f"Warmup failed: {e}")
            return False

    def shutdown(self) -> None:
        """No-op for Ollama (stateless HTTP)."""
        pass

    def generate_embedding(self, text: str) -> List[float]:
        """Generate vector embedding for a given text."""
        if not text:
            return []
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": self.embedding_model, "prompt": text}
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []

    def analyze_article(self, text: str, context: str = "") -> Dict[str, Any]:
        """Analyze article text using the LLM to get summary, relevance, and impact."""
        clipped_text = text[:4000]

        prompt_template = ""
        try:
            with open("prompts.yaml", "r") as f:
                import yaml
                data = yaml.safe_load(f)
                prompt_template = data.get("analysis_prompt", "")
        except Exception as e:
            logger.error(f"Failed to load prompts.yaml: {e}")

        if not prompt_template:
            logger.warning("Using fallback prompt")
            prompt_template = (
                "You are a business intelligence analyst.\n"
                "SECTION 1: STRATEGIC CONTEXT: {context}\n"
                "SECTION 2: ARTICLE TEXT: {clipped_text}\n"
                "TASK: Return JSON with summary, relevance_score (1-10), "
                "relevance_reasoning, impact_score (1-10), key_entities."
            )

        prompt = prompt_template.format(context=context, clipped_text=clipped_text)
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
        prompt = (
            "Return ONLY JSON with a single field:\n"
            '- topics: list[str] of 3-6 short, meaningful topic tags (2-4 words each).\n'
            "Avoid generic words, focus on the main themes.\n\n"
            f"ARTICLE TEXT:\n{clipped_text}"
        )
        response = self.generate_json(prompt)
        topics = response.get("topics", []) if response else []
        if not isinstance(topics, list):
            return []
        cleaned = [str(topic).strip() for topic in topics if str(topic).strip()]
        return cleaned[:max_topics]

    def generate_json(self, prompt: str, timeout: int = 300) -> Dict[str, Any]:
        """Helper to request a JSON-formatted response from Ollama."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        try:
            logger.info("⏳ Calling LLM (this may take 30-60 seconds)...")
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            logger.info("✓ LLM response received")
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

    def generate_text(self, prompt: str, timeout: int = 300) -> str:
        """Generate plain text from Ollama."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as exc:
            logger.error("Error calling Ollama text endpoint: %s", exc)
            return ""
