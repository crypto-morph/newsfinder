# News Finder

A competitive intelligence dashboard that aggregates, filters, and analyzes news articles for specific company goals. It uses **Ollama** (or **Kiro CLI**) for LLM inference and **ChromaDB** for vector search (RAG).

## Features

- **Multi-Company Monitoring**: Track a primary company plus multiple competitors.
- **Intelligent Ingestion**:
    - Scrapes full article content from RSS feeds.
    - **LLM Analysis**: Summarizes articles and scores them for "Relevance" and "Impact".
    - **Keyword Filtering**: Pre-filters noise based on broad keywords.
- **LLM Verification**: Audits local model scores against a remote provider, with prompt optimization tooling.
- **Archive Import**: Backfill historical data from BBC Archive sitemaps by selecting a specific month.
- **Context Profiling**: Automatically scrapes company websites to generate "Strategic Context" (Goals, Products, Market Position) for the AI.
- **RAG Explorer**: Semantic search across your news database.
- **Modern UI**: Custom Flask dashboard with real-time pipeline progress via System Console.

## Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** for dependency management and running scripts.
- **Ollama** installed and running locally (for embeddings, and optionally for inference).
    - Models required: `nomic-embed-text` (embedding) and optionally `llama3.1:8b` (inference if not using Kiro provider).

## Quick Start

1.  **Clone & Setup**:
    ```bash
    git clone <repo-url>
    cd newsfinder
    uv sync
    ```

2.  **Pull Embedding Model**:
    ```bash
    ollama pull nomic-embed-text
    ```

3.  **Run the System**:
    ```bash
    ./newsctl start
    ```
    This starts the web UI on `http://0.0.0.0:5000`.

4.  **Configure**:
    - Go to **Config & Context** (`/config`).
    - Add your **Primary Company** URL (e.g., your own site).
    - Add **Competitor** URLs.
    - Click **"Refresh All Profiles"** to let the AI analyze the companies.
    - Click **"Generate with AI"** to create a starting list of filtering keywords.

5.  **Ingest News**:
    - **Real-time**: Go to **Dashboard** and click **"Run Pipeline"** (or use the System Console).
    - **Historical**: Go to **Import** (`/import`), select a month, and click **"Start Backfill"**.

## Configuration (`config.yaml`)

The system is controlled by `config.yaml`. You can edit this file directly or use the UI.

```yaml
companies:
  - name: My Company
    url: https://mycompany.com
  - name: Competitor A
    url: https://comp-a.com

feeds:
  - name: BBC Health
    url: https://feeds.bbci.co.uk/news/health/rss.xml

pipeline:
  keywords: [ "health", "wellness", "diagnostics" ]
  alert_threshold:
    relevance: 6
    impact: 5

llm:
  provider: kiro          # Options: "ollama" or "kiro"
  base_url: http://localhost:11434
  model: null             # null = use provider default
  embedding_model: nomic-embed-text:latest
  effort: low             # ACP effort level: low, medium, high
  prompt_rules: []        # Custom rules for AI analysis
```

## Directory Structure

```
/newsfinder
  /src/
    /aggregator/    # RSS scraper & Sitemap backfiller
    /analysis/      # LLM client & Verification logic
    /database/      # ChromaDB wrapper
    /services/      # Shared business logic (tagging, scraping)
    /web/           # Flask Application
      /routes/      # Modular Blueprints (dashboard, articles, api...)
      /templates/   # Jinja2 HTML templates
    main.py         # Entry point / Scheduler
  /data/
    /archive/       # Parquet monthly archives
  /scripts/         # CLI utilities
  config.yaml       # Configuration
  pyproject.toml    # Dependencies (uv)
```

## CLI Tools

- `./newsctl start|stop|restart|status`: Manage the web server process.
- `./newsctl pipeline`: Run the ingestion pipeline from the command line.
- `./newsctl profile`: Refresh all company context profiles.
- `./newsctl import <args>`: Command-line backfilling (alternative to UI).

## Development

To run in debug mode:
```bash
uv run python src/main.py
```

## License

Proprietary / Internal Use Only.
