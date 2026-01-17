# News Finder

A competitive intelligence dashboard that aggregates, filters, and analyzes news articles for specific company goals. It uses **Ollama** for local LLM inference and **ChromaDB** for vector search (RAG).

![Dashboard Preview](https://via.placeholder.com/800x400?text=News+Finder+Dashboard)

## Features

- **Multi-Company Monitoring**: Track a primary company plus multiple competitors.
- **Intelligent Ingestion**:
    - Scrapes full article content from RSS feeds.
    - **LLM Analysis**: Summarizes articles and scores them for "Relevance" and "Impact".
    - **Keyword Filtering**: Pre-filters noise based on broad keywords.
- **Context Profiling**: Automatically scrapes company websites to generate "Strategic Context" (Goals, Products, Market Position) for the AI.
- **Discovery Mode**: View unfiltered news to spot missing keywords.
- **RAG Explorer**: Semantic search across your news database.
- **Modern UI**: Clean Flask + Bulma dashboard with real-time pipeline progress.

## Prerequisites

- **Python 3.10+**
- **Ollama** installed and running locally.
    - Models required: `llama3.1:8b` (inference) and `all-minilm` (embedding).

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
    ollama pull all-minilm
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
    - Go to **Dashboard**.
    - Click **"Run Pipeline"**.
    - Watch as articles are fetched, analyzed, and scored in real-time.

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
  embedding_model: all-minilm
```

## Directory Structure

- `src/aggregator`: RSS fetching and HTML scraping logic.
- `src/analysis`: LLM client and prompt engineering.
- `src/context_profiler`: Logic for scraping company sites and generating strategy profiles.
- `src/database`: ChromaDB wrapper.
- `src/web`: Flask application and Jinja2 templates.
- `logs/`: Application logs and feedback data.
- `chroma_db/`: Vector database storage (git-ignored).

## Development

To run in debug mode:
```bash
source venv/bin/activate
python src/web/app.py
```

## License

Proprietary / Internal Use Only.
