# News Finder Progress Report

## Summary
The News Finder system is fully implemented. It supports multi-company competitive monitoring, intelligent news ingestion, AI-driven analysis (summary, relevance, impact), vector-based retrieval (RAG), and a comprehensive web dashboard. Key features include a granular API-driven pipeline, unfiltered "Discovery" mode, manual and AI-assisted tag management, and configurable multi-company context profiling.

## Status vs. spec.md

### ✅ Implemented
- **RSS news aggregation** (BBC/Guardian/etc.) with article scraping. @src/aggregator/rss_scraper.py
- **LLM analysis + embeddings** via Ollama (summary/relevance/impact/entities + embeddings). @src/analysis/llm_client.py
- **ChromaDB storage** with add/query/delete + recent peek. @src/database/chroma_client.py
- **Multi-Company Context Profiler** generating structured profiles for Primary + Competitors. @src/context_profiler.py
- **Granular Ingestion Pipeline** exposed via API endpoints (`/api/pipeline/fetch`, `/api/pipeline/process`). @src/pipeline.py
- **Flask UI app** with Dashboard, Explorer, Discovery, Sources, and Config views. @src/web/app.py
- **Dashboard**: Real-time pipeline progress, deduped articles, goal filtering, score visualization.
- **Discovery**: Unfiltered feed view to identify new keywords.
- **Config**: Manage companies, profiles (auto + manual edit), and filtering keywords.
- **Tag Management**: Edit tags, regenerate with AI, report bad tags.
- **Sources**: Manage RSS feeds with live preview.
- **Config loader** with migration support for multi-company schema. @src/settings.py
- **Tag feedback loop** for logging corrections. @src/feedback.py
- **Verification Service**: Multi-model auditing via OpenRouter (Gemini/GPT-4o) to flag hallucinations. @src/analysis/verification_service.py
- **Parquet Archiving**: Unified storage for scraped data and Hugging Face datasets (`data/archive/YYYY-MM/`). @src/archive_manager.py
- **Hugging Face Sync**: Tools to download monthly archives directly from HF. @scripts/sync_hf_archive.py
- **Prompt Hardening**: Strict scoring rules to prevent hallucinations (Geography, Analogies, Evidence Quotes).

### 🚧 In Progress / Partial
- **Scheduler**: Currently manual run via UI. `APScheduler` dependency exists but no `main.py` entrypoint for automated background runs yet (UI-driven workflow preferred by user for now).

### ❌ Missing / Planned
- **Slack Integration**: Not requested in current scope.

## Spec alignment notes
- **Strategic Context**: LLM prompt updated to consider "Strategic Landscape" (Primary vs Competitors) for impact scoring.
- **Relevance scoring**: Driven by structured goals of the *Primary* company.
- **Geography Constraint**: Strictly limited to UK & Ireland for relevance scoring.

## Next Recommended Steps
1.  **Backfill History**: Run `python scripts/sync_hf_archive.py --start 2024-01` to get historical data.
2.  **Verify**: Use the new "LLM Verification" tab to check the local model's accuracy.
3.  **Tune**: Adjust keywords in the UI based on what you find in Discovery mode.

## Notes
- Triple-quote syntax bug in `context_profiler.py` fixed.
- Missing `os` import in profiler fixed.
- UI loading states added for better UX on long-running AI tasks.
