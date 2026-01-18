import json
import time
import sys
import os
import argparse
from typing import List, Dict, Any

# Add project root to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.llm_client import OllamaClient

# Standard context for the benchmark
BENCHMARK_CONTEXT = """
PRIMARY COMPANY: Bluecrest Wellness
Business: Affordable, nationwide health screening and wellness packages for individuals and employers.
Goals: Expand preventive health screening reach across the UK; Promote early detection services.

COMPETITORS: Nuffield Health, Randox Health, Bupa.
"""

def load_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _parse_score(score_val: Any) -> int:
    """Helper to safely parse relevance score to int."""
    if isinstance(score_val, int):
        return score_val
    if isinstance(score_val, float):
        return int(score_val)
    if isinstance(score_val, str):
        # Handle cases like "7" or "7 (High)" or "Score: 7"
        import re
        # Find the first sequence of digits
        match = re.search(r'\d+', score_val)
        if match:
            return int(match.group())
    return 0

def evaluate_model(model_name: str, dataset: List[Dict[str, Any]], base_url: str) -> Dict[str, Any]:
    print(f"\nEvaluating model: {model_name}...")
    client = OllamaClient(base_url=base_url, model=model_name)
    
    # Warmup
    start_warm = time.time()
    if not client.warmup():
        print(f"  Warning: Model {model_name} failed to warmup.")
    warmup_time = time.time() - start_warm
    
    results = {
        "model": model_name,
        "warmup_time": warmup_time,
        "total_time": 0,
        "avg_time_per_doc": 0,
        "articles": []
    }
    
    start_run = time.time()
    
    for item in dataset:
        print(f"  Processing: {item['id']}...", end="", flush=True)
        t0 = time.time()
        
        # We'll use the title + content as the text to analyze
        full_text = f"{item['title']}\n\n{item['content']}"
        
        try:
            analysis = client.analyze_article(full_text, context=BENCHMARK_CONTEXT)
            duration = time.time() - t0
            
            # Simple heuristic for accuracy based on expected relevance
            # "high" -> 7-10, "medium" -> 4-6, "low" -> 1-3
            raw_score = analysis.get("relevance_score", 0)
            score = _parse_score(raw_score)
            expected = item.get("expected_relevance")
            
            match = False
            if expected == "high" and score >= 7: match = True
            elif expected == "medium" and 4 <= score <= 6: match = True
            elif expected == "low" and score <= 3: match = True
            
            print(f" {duration:.2f}s | Score: {score} ({expected}) | Match: {'✅' if match else '❌'}")
            
            results["articles"].append({
                "id": item["id"],
                "duration": duration,
                "score": score,
                "raw_score": raw_score,
                "expected": expected,
                "match": match,
                "reasoning": analysis.get("relevance_reasoning"),
                "summary": analysis.get("summary")
            })
            
        except Exception as e:
            print(f" Error: {e}")
            results["articles"].append({
                "id": item["id"],
                "error": str(e)
            })

    results["total_time"] = time.time() - start_run
    if dataset:
        results["avg_time_per_doc"] = results["total_time"] / len(dataset)
        
    return results

def print_report(all_results: List[Dict[str, Any]]):
    print("\n" + "="*80)
    print(f"{'BENCHMARK REPORT':^80}")
    print("="*80)
    
    # Summary Table
    print(f"{'Model':<30} | {'Warmup':<8} | {'Avg (s)':<8} | {'Accuracy':<8} | {'Total (s)':<8}")
    print("-" * 80)
    
    for res in all_results:
        articles = res["articles"]
        matches = sum(1 for a in articles if a.get("match"))
        accuracy = (matches / len(articles)) * 100 if articles else 0
        
        print(f"{res['model']:<30} | {res['warmup_time']:<8.2f} | {res['avg_time_per_doc']:<8.2f} | {accuracy:<7.0f}% | {res['total_time']:<8.2f}")

    print("\nDetailed Failures:")
    for res in all_results:
        failures = [a for a in res["articles"] if not a.get("match") and not a.get("error")]
        if failures:
            print(f"\nModel: {res['model']}")
            for f in failures:
                print(f"  - {f['id']}: Expected {f['expected']}, got {f['score']}")
                print(f"    Reasoning: {f['reasoning']}")

def main():
    parser = argparse.ArgumentParser(description="Benchmark Ollama models for News Finder")
    parser.add_argument("--models", nargs="+", help="List of models to test", default=["qwen2.5:1.5b"])
    parser.add_argument("--dataset", default="benchmarks/dataset.json", help="Path to dataset")
    parser.add_argument("--url", default="http://localhost:11434", help="Ollama base URL")
    
    args = parser.parse_args()
    
    try:
        dataset = load_dataset(args.dataset)
    except Exception as e:
        print(f"Failed to load dataset: {e}")
        return

    all_results = []
    for model in args.models:
        all_results.append(evaluate_model(model, dataset, args.url))
        
    print_report(all_results)

    # Save full results
    with open("benchmarks/results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print("\nFull results saved to benchmarks/results.json")

if __name__ == "__main__":
    main()
