# News Finder

A competitive intelligence dashboard that aggregates, filters, and analyzes news articles for specific company goals. It uses **Ollama** for local LLM inference and **ChromaDB** for vector search (RAG).

![Dashboard Preview](https://via.placeholder.com/800x400?text=News+Finder+Dashboard)

## Features

- **Multi-Company Monitoring**: Track a primary company plus multiple competitors.
- **Intelligent Ingestion**:
    - Scrapes full article content from RSS feeds.
    - **LLM Analysis**: Summarizes articles and scores them for "Relevance" and "Impact".
    - **Keyword Filtering**: Pre-filters noise based on broad keywords.
- **Archive Import**: Backfill historical data from BBC Archive sitemaps by selecting a specific month.
- **Context Profiling**: Automatically scrapes company websites to generate "Strategic Context" (Goals, Products, Market Position) for the AI.
- **RAG Explorer**: Semantic search across your news database.
- **Modern UI**: Clean Flask + Bulma dashboard with real-time pipeline progress.

## Prerequisites

- **Python 3.10+**
- **Ollama** installed and running locally.
    - Models required: `llama3.1:8b` (inference) and `nomic-embed-text` or `all-minilm` (embedding).

## Quick Start

1.  **Clone & Setup**:
    ```bash
    git clone <repo-url>
    cd newsfinder
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

2.  **Pull AI Models**:
    ```bash
    ollama pull llama3.1:8b
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
    - **Real-time**: Go to **Dashboard** and click **"Run Pipeline"**.
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
    relevance: 7
    impact: 7

llm:
  model: llama3.1:8b
  embedding_model: nomic-embed-text
```

## Directory Structure

```
/newsfinder
  /venv/            # IGNORED
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
  config.yaml       # Configuration
  requirements.txt
```

## CLI Tools

- `./newsctl start|stop|restart`: Manage the web server process.
- `scripts/backfill_sitemaps.py`: Standalone script for command-line backfilling (alternative to UI).
- `scripts/warm_sitemap_cache.py`: Pre-builds the sitemap index cache for faster imports.

## Development

To run in debug mode:
```bash
source venv/bin/activate
python src/main.py
```

## License

Proprietary / Internal Use Only.
