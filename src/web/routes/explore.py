from flask import Blueprint, render_template, request
from src.web.utils import current_config, get_db, build_ollama
from typing import List, Dict, Any

explore_bp = Blueprint("explore", __name__)

@explore_bp.route("/explore")
def explore():
    cfg = current_config()
    query = request.args.get("q", "").strip()
    results: List[Dict[str, Any]] = []

    if query:
        ollama = build_ollama(cfg)
        embedding = ollama.generate_embedding(query)
        if embedding:
            raw = get_db().query_articles(embedding, n_results=5)
            ids = raw.get("ids", [[]])[0]
            docs = raw.get("documents", [[]])[0]
            metas = raw.get("metadatas", [[]])[0]
            distances = raw.get("distances", [[]])[0]
            for idx, item_id in enumerate(ids):
                summary = docs[idx] if idx < len(docs) else ""
                metadata = metas[idx] if idx < len(metas) else {}
                score = distances[idx] if idx < len(distances) else None
                results.append(
                    {
                        "id": item_id,
                        "summary": summary,
                        "metadata": metadata,
                        "score": score,
                    }
                )

    return render_template(
        "explore.html",
        query=query,
        results=results,
        active_page="explore",
    )
