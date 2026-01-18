import os
import requests
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class OpenRouterClient:
    def __init__(self, model: str = "google/gemini-2.0-flash-001"):
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = model
        
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not found in environment variables. Verification will be disabled.")

    def check_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            # Simple list models call to check auth
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"OpenRouter connection check failed: {e}")
            return False

    def analyze_article(self, text: str, context: str = "") -> Dict[str, Any]:
        """
        Analyze article using OpenRouter model to verify local model's work.
        Returns a JSON object compatible with the local analysis format.
        """
        if not self.api_key:
            return {}

        clipped_text = text[:8000] # Big models can handle more context
        
        prompt = f"""
        You are a Senior Business Intelligence Auditor.
        
        STRATEGIC CONTEXT (Primary Company & Competitors):
        {context}
        
        ARTICLE TEXT:
        {clipped_text}
        
        TASK:
        Review this article and provide an independent assessment of its relevance to the Primary Company.
        
        SCORING GUIDELINES:
        - 0-3 (Low): Irrelevant topics (Sports, Entertainment, Politics without healthcare angle).
        - 4-6 (Medium): Tangential (General healthcare trends, adjacent technology).
        - 7-10 (High): Direct Relevance (Competitors, specific industry regulations, core business).
        
        RESPONSE FORMAT:
        Return ONLY valid JSON with no markdown formatting:
        {{
            "summary": "Concise summary",
            "relevance_score": Integer 1-10,
            "relevance_reasoning": "Explanation of the score",
            "impact_score": Integer 1-10,
            "key_entities": ["list", "of", "entities"]
        }}
        """

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:5000", # Required by OpenRouter
            "X-Title": "NewsFinder Local",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"}
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Parse JSON from content
            try:
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Sometimes models wrap in markdown code blocks despite instructions
                import re
                match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
                return {}
                
        except Exception as e:
            logger.error(f"OpenRouter analysis failed: {e}")
            return {}
