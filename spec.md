# News Finder Specification

An agentic system for gathering recent news articles on a particular topic, summarizing them, storing them in a RAG database, and providing alerts/insights relevant to specific company goals.

## 1. Architecture & Tech Stack

- **Language**: Python 3.x
- **Environment Management**: `venv` (Virtual Environment)
- **LLM Engine**: [Ollama](https://ollama.com/)
  - **Inference Model**: `LiquidAI/LFM2.5-1.2B-Instruct` (via Ollama) or similar small, CPU-friendly model.
  - **Embedding Model**: `nomic-embed-text` or `all-minilm` (via Ollama) for RAG vectorization.
- **Database**: [ChromaDB](https://www.trychroma.com/) (Vector Store for RAG)
- **Web Framework**: Flask (using Blueprints for modularity)
- **Frontend**: HTML templates with [Bulma CSS](https://bulma.io/)
- **Scheduling**: `APScheduler` or native Python `schedule`

## 2. Core Concepts

### RAG (Retrieval-Augmented Generation) Workflow
1.  **Ingest**: News is fetched -> Summarized -> Converted to Vectors (Embeddings) -> Stored in ChromaDB.
2.  **Retrieve**: User queries (or automated alerts) -> Query converted to Vector -> Math search in ChromaDB -> Relevant context found.
3.  **Generate**: Context + Original Query sent to LLM -> LLM generates informed answer.

## 3. Components

### 3.1. Company Context Profiler
*Functionality*: "Grounds" the system in the competitive landscape.
- **Input**: List of Company URLs (Primary + Competitors).
- **Process**: Scrapes company websites (Landing page, About Us).
- **Output**: A structured profile for each company containing:
    - Offer Summary
    - Business Goals
    - Key Products/Services
    - Market Position
    - Focus Keywords
- **Storage**: Saved as `company_context.txt` (combined prompt) and `.json` (structured data).
- **Manual Override**: Users can manually edit generated profiles via the UI.

### 3.2. News Aggregator
*Functionality*: Fetches raw content.
- **Sources**: 
    - RSS Feeds (configured via UI or YAML).
- **Frequency**: On-demand via UI or manual run.
- **Filter**: 
    - **Keyword Filtering**: Articles must match at least one configured keyword.
    - **Archiving**: Automatically saves fetched articles to Parquet archives.

### 3.3. Archive Import (Backfill)
*Functionality*: Fills gaps in historical data.
- **Source**: BBC Archive Sitemaps.
- **Process**:
    - Scans sitemap index to find monthly archives.
    - Filters URLs by selected month.
    - Scrapes content and processes through the ingestion pipeline.
- **UI**: Dedicated "Import" tab to trigger backfills.

### 3.4. Intelligent Ingestion Pipeline
*Functionality*: Processes raw HTML/Text into structured data via Granular APIs.
1.  **Fetch**: Retrieve raw articles from feeds or Sitemap Backfiller.
2.  **Process (Per Article)**:
    - **Deduplicate**: Check hash of URL against DB.
    - **Filter**: Apply keyword allowlist.
    - **Analyze (LLM)**: 
        - Summarize the article.
        - Score "Relevance" (1-10) to the *Primary* company.
        - Score "Impact" (1-10) on the broader market/competitors.
        - Extract "Key Entities" and "Topic Tags".
    - **Verify (Optional)**: Cross-check high-value articles with a secondary LLM.
    - **Embed**: Generate vector embeddings for the summary.
    - **Store**: Save to ChromaDB.
    - **Alert**: Log high-scoring articles.

### 3.5. RAG Database (ChromaDB)
- **Collection Name**: `news_articles`
- **Metadata Fields**:
    - `url`, `title`, `published_date`, `source`
    - `relevance_score`, `impact_score`
    - `summary_text`
    - `topic_tags`, `key_entities`, `goal_matches`

### 3.6. Verification Service
*Functionality*: auditing and quality control.
- **Trigger**: Random sample (10%) or High Interest articles (100%).
- **Process**: Sends article + local analysis to an external superior model.
- **Output**: Agrees/Disagrees with local score. Flags hallucinations.
- **UI**: Dedicated "Verification" tab to review audit logs.

### 3.7. Alert System
*Functionality*: Proactive notification.
- **Trigger**: New article ingested with `relevance_score > 7` AND `impact_score > 7`.
- **Channel**: Appended to a local `alerts.log` file and displayed on Dashboard.

### 3.8. User Interface (Web Dashboard)
*Style*: Modern, Clean, Bulma CSS.
- **Dashboard View**: System Status, Recent Alerts, Latest Articles.
- **Articles View**: List processed articles, edit tags, view history log, re-appraise.
- **Import View**: Backfill from archives.
- **Verification View**: Audit log comparing Local vs Remote LLM scores.
- **RAG Explorer**: Semantic search across the article database.
- **Sources View**: Manage RSS feeds and preview content.
- **Config View**: Manage Company Profiles and Keywords.

## 4. Development Guidelines

### Structure
```
/newsfinder
  /venv/            # IGNORED
  /src/
    /aggregator/    # Scrapers & Sitemap logic
    /analysis/      # LLM, Embedding, & Verification logic
    /database/      # ChromaDB wrappers
    /services/      # Shared business logic (tagging, scraping)
    /web/           # Flask App
      /routes/      # Blueprints (dashboard, articles, etc.)
      /templates/   # Jinja2 templates
    main.py         # Entry point / Scheduler
  /data/
    /archive/       # Parquet archives
  config.yaml       # Configuration
  requirements.txt
```

### Git Rules
- `.gitignore` must include:
    - `venv/`
    - `__pycache__/`
    - `*.env`
    - `chroma_db/`
    - `logs/`
    - `document-cache/`
    - `data/archive/`

## 5. Context

Bluecrest Wellness (https://bluecrestwellness.com/) is the primary context. Scoring is based on relevance to health screenings, preventive health, and wellness packages.

## 6. Roadmap
1.  **Phase 1 (Core)**: Setup Python, Chroma, Ollama connection. Build basic scraper. [Completed]
2.  **Phase 2 (Intelligence)**: Implement Company Context Profiler and LLM Scoring pipeline. [Completed]
3.  **Phase 3 (UI)**: Build Bulma dashboard. [Completed]
4.  **Phase 4 (Polish)**: Scheduler, Logging, Refinement. [Completed]
5.  **Phase 5 (Refactor & Scale)**: Modular Blueprints, Backfill tools, Robust Scraping. [Completed]
