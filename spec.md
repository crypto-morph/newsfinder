# News Finder Specification

An agentic system for gathering recent news articles on a particular topic, summarizing them, storing them in a RAG database, and providing alerts/insights relevant to specific company goals.

## 1. Architecture & Tech Stack

- **Language**: Python 3.x
- **Environment Management**: `venv` (Virtual Environment)
- **LLM Engine**: [Ollama](https://ollama.com/)
  - **Inference Model**: `LiquidAI/LFM2.5-1.2B-Instruct` (via Ollama) or similar small, CPU-friendly model.
  - **Embedding Model**: `nomic-embed-text` or `all-minilm` (via Ollama) for RAG vectorization.
- **Database**: [ChromaDB](https://www.trychroma.com/) (Vector Store for RAG)
- **Web Framework**: Flask or FastAPI (for the UI backend)
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
- **Storage**: Saved as `company_context.txt` (combined prompt) and `.json` (structured data) to influence "Relevance" and "Impact" scoring.
- **Manual Override**: Users can manually edit generated profiles via the UI.

### 3.2. News Aggregator
*Functionality*: Fetches raw content.
- **Sources**: 
    - RSS Feeds (configured via UI or YAML).
- **Frequency**: On-demand via UI or manual run.
- **Filter**: 
    - **Keyword Filtering**: Articles must match at least one configured keyword.
    - **Discovery Mode**: A separate view to see unfiltered articles and discover new keywords.
    - **Archiving**: Automatically saves fetched articles to monthly compressed Parquet files (`data/archive/YYYY-MM/`).

### 3.3. Intelligent Ingestion Pipeline
*Functionality*: Processes raw HTML/Text into structured data via Granular APIs.
1.  **Fetch**: Retrieve raw articles from feeds or Parquet Archive.
2.  **Process (Per Article)**:
    - **Deduplicate**: Check hash of URL against DB.
    - **Filter**: Apply keyword allowlist.
    - **Analyze (LLM)**: 
        - Summarize the article.
        - Score "Relevance" (1-10) to the *Primary* company.
        - Score "Impact" (1-10) on the broader market/competitors.
        - Extract "Key Entities" and "Topic Tags".
    - **Verify (Optional)**: Cross-check high-value articles with a secondary LLM (e.g., via OpenRouter) to flag hallucinations.
    - **Embed**: Generate vector embeddings for the summary.
    - **Store**: Save to ChromaDB.
    - **Alert**: Log high-scoring articles.

### 3.4. RAG Database (ChromaDB)
- **Collection Name**: `news_articles`
- **Metadata Fields**:
    - `url`, `title`, `published_date`, `source`
    - `relevance_score`, `impact_score`
    - `summary_text`
    - `topic_tags`, `key_entities`, `goal_matches`

### 3.5. Verification Service
*Functionality*: auditing and quality control.
- **Trigger**: Random sample (10%) or High Interest articles (100%).
- **Process**: Sends article + local analysis to an external superior model (e.g., Gemini Pro via OpenRouter).
- **Output**: Agrees/Disagrees with local score. Flags hallucinations.
- **UI**: Dedicated "Verification" tab to review audit logs.

### 3.6. Alert System
*Functionality*: Proactive notification.
- **Trigger**: New article ingested with `relevance_score > 7` AND `impact_score > 7`.
- **Channel**: Appended to a local `alerts.log` file and displayed on Dashboard.

### 3.7. User Interface (Web Dashboard)
*Style*: Modern, Clean, Bulma CSS.
- **Dashboard View**:
    - System Status & Recent Alerts.
    - List of recent articles with scores, tags, and goal matches.
    - **Article Actions**: Edit Tags (with AI regeneration), Delete Article.
    - **Filtering**: By Primary Company match or specific Business Goal.
    - **Run Pipeline**: Interactive, real-time progress bar processing articles one-by-one.
- **Discovery View**:
    - View unfiltered feed items to spot missed news.
    - "Add Keyword" shortcuts for rapid tuning.
- **Verification View**:
    - Audit log comparing Local vs Remote LLM scores.
- **RAG Explorer**:
    - Semantic search across the article database.
- **Sources View**:
    - Add/remove RSS feeds.
    - Live preview of feed content.
- **Config View**:
    - **Multi-Company Management**: Add/Edit/Remove monitored companies (Primary + Rivals).
    - **Profile Management**: View AI-generated profiles, refresh context, or manually edit fields.
    - **Keyword Management**: Tag-based UI to add/remove filtering keywords.
    - **AI Generators**: "Generate Keywords" button to suggest terms based on company context.

## 4. Development Guidelines

### Structure
```
/newsfinder
  /venv/            # IGNORED in git
  /src/
    /aggregator/    # Scrapers & Archive Manager
    /analysis/      # LLM, Embedding, & Verification logic
    /database/      # ChromaDB wrappers
    /web/           # Flask/FastAPI app & Templates
    main.py         # Entry point / Scheduler
  /data/
    /archive/       # Parquet monthly archives
  config.yaml       # Configuration (URLs, Keys)
  requirements.txt
  .gitignore
  README.md
```

### Git Rules
- `.gitignore` must include:
    - `venv/`
    - `__pycache__/`
    - `*.env`
    - `chroma_db/` (The local database files)
    - `logs/`
    - `document-cache/` (Legacy JSON cache)
    - `data/archive/` (Parquet files - too large for git)


## 5. Context

Bluecrest Wellness are a health company with main website at https://bluecrestwellness.com/.

You will need analyse their core business and define the "relevance" and "impact" scores for each article based on Bluecrest objective.

The "relevance" score should be based on how directly the article relates to Bluecrest's core business areas (e.g., health screenings, preventive health, wellness packages).

The "impact" score should be based on how likely the article is to influence Bluecrest's business (e.g., if it mentions a new health trend that Bluecrest could capitalize on).

You will need to build a script which will convert the company context into a structured format that identifies the main goals of the company and uses them as a basis for scoring articles. The structured output should include:
- company_name
- offer_summary
- business_goals
- key_products
- market_position
- focus_keywords

## 6. Roadmap
1.  **Phase 1 (Core)**: Setup Python, Chroma, Ollama connection. Build basic scraper for BBC.
2.  **Phase 2 (Intelligence)**: Implement Company Context Profiler and LLM Scoring pipeline.
3.  **Phase 3 (UI)**: Build Bulma dashboard to view data.
4.  **Phase 4 (Polish)**: Scheduler, Logging, Refinement.
