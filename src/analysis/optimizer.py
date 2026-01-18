import yaml
import logging
import json
import os
from typing import List, Dict, Any, Tuple
from src.analysis.llm_client import OllamaClient
from src.analysis.openrouter_client import OpenRouterClient
from src.analysis.verification_service import VerificationService

logger = logging.getLogger(__name__)

class PromptOptimizer:
    def __init__(self, config_path: str = "config.yaml", prompts_path: str = "prompts.yaml"):
        self.config_path = config_path
        self.prompts_path = prompts_path
        self.local_client = OllamaClient() # Config loaded internally or defaults
        self.remote_client = OpenRouterClient(model="google/gemini-2.0-flash-001") # Or load from config if needed
        self.verification_service = VerificationService({"verification": {"log_file": "logs/verification.jsonl"}}) # Simplification for now

    def load_current_prompt(self) -> str:
        try:
            with open(self.prompts_path, "r") as f:
                data = yaml.safe_load(f)
                return data.get("analysis_prompt", "")
        except Exception as e:
            logger.error(f"Failed to load prompts.yaml: {e}")
            return ""

    def get_failure_cases(self, limit: int = 5) -> List[Dict]:
        """
        Retrieve recent flagged verification records.
        """
        # We need to read the log file directly or use the service if it exposes what we need
        # The service exposes get_recent_verifications
        recent = self.verification_service.get_recent_verifications(limit=100)
        
        # Filter for flagged items (discrepancy >= 4)
        failures = [r for r in recent if r.get("flagged")]
        return failures[:limit]

    def generate_optimized_prompt(self, current_prompt: str, failures: List[Dict]) -> str:
        """
        Ask the superior model to improve the prompt based on failure cases.
        """
        if not self.remote_client.api_key:
            return "Error: OpenRouter API Key missing."

        # Format failures for the prompt
        examples = ""
        for i, f in enumerate(failures):
            examples += f"""
            CASE {i+1}:
            Article: {f.get('article_title')}
            Local Score (Bad): {f.get('local_score')}
            Remote Score (Correct): {f.get('remote_score')}
            Remote Reasoning: {f.get('remote_reasoning')}
            ------------------------------------------------
            """

        meta_prompt = f"""
        You are an expert Prompt Engineer optimizing a local LLM for a specific business intelligence task.
        
        CURRENT PROMPT:
        {current_prompt}
        
        FAILURE CASES (Where the local LLM hallucinated or scored incorrectly):
        {examples}
        
        TASK:
        Rewrite the CURRENT PROMPT to address these specific failure modes.
        - Add or refine "NEGATIVE CONSTRAINTS" to prevent these specific hallucinations.
        - Clarify "SCORING GUIDELINES" to align with the Remote Score logic.
        - Keep the prompt structure (SECTION 1, SECTION 2, TASK, GUIDELINES, CONSTRAINTS, FORMAT).
        - Do not remove essential instructions, just refine them.
        
        Return ONLY the full text of the NEW PROMPT. Do not include markdown formatting like ```yaml or ```text.
        """
        
        # We use a direct chat completion here since OpenRouterClient.analyze_article is specific to articles
        # We'll use a raw request helper or add one to OpenRouterClient. 
        # For now, let's just use requests directly here to avoid modifying OpenRouterClient too much if not needed,
        # OR we can assume we can add a helper method to OpenRouterClient? 
        # Actually OpenRouterClient has no generic chat method exposed cleanly. 
        # Let's add a generic generate method to OpenRouterClient or just implement it here.
        # Implementation here:
        
        import requests
        headers = {
            "Authorization": f"Bearer {self.remote_client.api_key}",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "NewsFinder Optimizer",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.remote_client.model,
            "messages": [{"role": "user", "content": meta_prompt}]
        }
        
        try:
            resp = requests.post(
                f"{self.remote_client.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            
            # Strip markdown code blocks if present
            content = content.replace("```yaml", "").replace("```", "").strip()
            return content
            
        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            return ""

    def test_prompt(self, prompt_text: str, test_cases: List[Dict]) -> List[Dict]:
        """
        Run the provided prompt against the test cases using the local LLM.
        We need to simulate the `analyze_article` call but injecting the specific prompt.
        """
        results = []
        
        # We need to temporarily patch the prompt loading or just manually format it
        # The OllamaClient.analyze_article loads from file. 
        # We can reproduce the formatting logic here.
        
        for case in test_cases:
            # We need the full article content? 
            # The verification log might not have full content. 
            # Ideally we fetch the article from DB or cache using the URL.
            # For this prototype, we might have to rely on what's available or fetch.
            # Verification log only has title/url.
            # We need to fetch content.
            
            # Attempt to fetch from DB?
            # We don't have DB access here easily without importing Pipeline/DB.
            # Let's import NewsDatabase
            from src.database.chroma_client import NewsDatabase
            db = NewsDatabase()
            
            # Try to find by URL or we just skip if not found?
            # Or use the URL if we can scrape? No, stick to DB content for speed/consistency.
            # Verification logs have 'article_url'.
            
            # Since we don't store URL as ID directly in Chroma (hashed), we need to re-hash.
            import hashlib
            article_id = hashlib.sha256(case['article_url'].encode("utf-8")).hexdigest()
            article = db.get_article(article_id)
            
            if not article:
                # Can't test if we don't have content
                results.append({
                    "title": case['article_title'],
                    "error": "Content not found in DB"
                })
                continue
                
            content = article.get("summary_text", "") # Wait, summary_text is the summary. We want full content? 
            # Chroma stores 'documents' which is Summary. 
            # If we don't store full content in Chroma, we can't fully re-test the prompt generation 
            # because the prompt runs on 'clipped_text' (full content).
            # The pipeline runs analysis on 'content' THEN stores summary.
            # If we don't archive full content, we are stuck.
            
            # Archive Manager? Parquet?
            # We can try to load from cache if available?
            # 'document-cache' dir has JSONs.
            cache_path = os.path.join("document-cache", f"{article_id}.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    cached = json.load(f)
                    full_text = cached.get("content", "")
            else:
                # If we can't find full text, we can't re-run analysis effectively.
                results.append({
                    "title": case['article_title'],
                    "error": "Full text source not found"
                })
                continue

            # Need context
            # Load context from file
            context = ""
            try:
                with open("logs/company_context.txt", "r") as f:
                    context = f.read()
            except:
                pass

            # Run Prompt
            formatted_prompt = prompt_text.format(context=context, clipped_text=full_text[:4000])
            response = self.local_client.generate_json(formatted_prompt)
            
            # Compare
            score = response.get("relevance_score", 0)
            target = case.get("remote_score", 0)
            
            results.append({
                "title": case['article_title'],
                "old_score": case['local_score'],
                "new_score": score,
                "target_score": target,
                "reasoning": response.get("relevance_reasoning", ""),
                "improved": abs(score - target) < abs(case['local_score'] - target)
            })
            
        return results

    def save_prompt(self, new_prompt: str) -> bool:
        try:
            with open(self.prompts_path, "w") as f:
                yaml.dump({"analysis_prompt": new_prompt}, f)
            return True
        except Exception as e:
            logger.error(f"Failed to save prompts: {e}")
            return False
