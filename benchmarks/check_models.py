import requests
import json
import sys

def list_models(base_url="http://localhost:11434"):
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
        data = response.json()
        models = data.get("models", [])
        
        print(f"{'Model Name':<40} | {'Size':<10} | {'Modified'}")
        print("-" * 70)
        
        for m in models:
            size_gb = m.get("size", 0) / (1024**3)
            print(f"{m['name']:<40} | {size_gb:.1f} GB    | {m['modified_at'][:10]}")
            
        return [m['name'] for m in models]
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:11434"
    list_models(url)
