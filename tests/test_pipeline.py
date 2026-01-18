import pytest
from unittest.mock import MagicMock, patch, mock_open
from src.pipeline import IngestionPipeline

@pytest.fixture
def mock_config():
    return {
        "feeds": [{"url": "http://feed.com", "name": "Feed"}],
        "llm": {
            "base_url": "http://localhost:11434",
            "model": "llama3",
            "embedding_model": "nomic-embed-text"
        },
        "storage": {
            "chroma_dir": "chroma_db",
            "context_cache": "logs/context.txt",
            "alerts_log": "logs/alerts.log",
            "status_file": "logs/status.json"
        },
        "pipeline": {
            "keywords": ["test"],
            "articles_per_feed": 5,
            "alert_threshold": {"relevance": 7, "impact": 7}
        }
    }

@pytest.fixture
def mock_deps():
    with patch("src.pipeline.load_config") as mock_load_config, \
         patch("src.pipeline.RSSNewsAggregator") as MockAggregator, \
         patch("src.pipeline.OllamaClient") as MockOllama, \
         patch("src.pipeline.VerificationService") as MockVerification, \
         patch("src.pipeline.NewsDatabase") as MockDB, \
         patch("src.pipeline.HistoryManager") as MockHistory:
        
        yield {
            "load_config": mock_load_config,
            "RSSNewsAggregator": MockAggregator,
            "OllamaClient": MockOllama,
            "VerificationService": MockVerification,
            "NewsDatabase": MockDB,
            "HistoryManager": MockHistory
        }

@pytest.fixture
def pipeline(mock_config, mock_deps):
    mock_deps["load_config"].return_value = mock_config
    return IngestionPipeline(config_path="dummy_config.yaml")

def test_fetch(pipeline, mock_deps):
    mock_aggregator_instance = mock_deps["RSSNewsAggregator"].return_value
    mock_aggregator_instance.fetch_recent_articles.return_value = [{"title": "Test"}]
    
    articles = pipeline.fetch()
    
    assert len(articles) == 1
    assert articles[0]["title"] == "Test"
    mock_aggregator_instance.fetch_recent_articles.assert_called_once()

def test_process_article_duplicate(pipeline, mock_deps):
    mock_db_instance = mock_deps["NewsDatabase"].return_value
    mock_db_instance.article_exists.return_value = True
    
    article = {"link": "http://test.com/dup", "title": "Dup", "content": "test content"}
    result = pipeline.process_article(article)
    
    assert result["status"] == "skipped"
    assert "Duplicate" in result["reason"]

def test_process_article_filtered(pipeline, mock_deps):
    mock_db_instance = mock_deps["NewsDatabase"].return_value
    mock_db_instance.article_exists.return_value = False
    
    # Content does not contain "test" keyword
    article = {"link": "http://test.com/filter", "title": "Filter", "content": "boring content"}
    result = pipeline.process_article(article)
    
    assert result["status"] == "skipped"
    assert "Filtered" in result["reason"]

def test_process_article_success(pipeline, mock_deps, mock_config):
    mock_db_instance = mock_deps["NewsDatabase"].return_value
    mock_db_instance.article_exists.return_value = False
    
    mock_ollama_instance = mock_deps["OllamaClient"].return_value
    mock_ollama_instance.analyze_article.return_value = {
        "summary": "Summary",
        "relevance_score": 8,
        "impact_score": 8,
        "key_entities": [],
        "relevance_reasoning": "Reason"
    }
    mock_ollama_instance.extract_topics.return_value = ["Topic"]
    mock_ollama_instance.generate_embedding.return_value = [0.1, 0.2]
    
    # Mock context file read
    with patch("builtins.open", mock_open(read_data="Context")):
        article = {
            "link": "http://test.com/ok",
            "title": "OK Article",
            "content": "This is a test content.",
            "published": "2023-01-01",
            "source": "Source"
        }
        result = pipeline.process_article(article)
        
        assert result["status"] == "imported"
        assert result.get("alert") is True # Scores are 8, threshold is 7
        
        # Verify DB add
        mock_db_instance.add_article.assert_called_once()
        args, kwargs = mock_db_instance.add_article.call_args
        assert kwargs["metadata"]["relevance_score"] == 8

def test_reprocess_article_success(pipeline, mock_deps):
    mock_db_instance = mock_deps["NewsDatabase"].return_value
    mock_aggregator_instance = mock_deps["RSSNewsAggregator"].return_value
    
    # Mock existing article
    mock_db_instance.get_article.return_value = {
        "url": "http://test.com/reprocess",
        "title": "Reprocess",
        "published": "2023-01-01",
        "source": "Source",
        "relevance_score": 5,
        "impact_score": 5
    }
    
    # Mock scraper returning content
    mock_aggregator_instance._scrape_article_content.return_value = "Updated test content."
    
    # Mock process_article logic (we can check if db.add_article is called again)
    # But since process_article is also on the pipeline instance, we might want to mock it?
    # Or just let it run. Let's let it run but we need to mock db.article_exists to return False or use force=True
    # The code calls process_article(..., force=True), so we don't need to worry about exists check.
    
    mock_ollama_instance = mock_deps["OllamaClient"].return_value
    mock_ollama_instance.analyze_article.return_value = {
        "summary": "Summary",
        "relevance_score": 9,
        "impact_score": 9
    }
    mock_ollama_instance.extract_topics.return_value = ["Topic1", "Topic2"]
    mock_ollama_instance.generate_embedding.return_value = [0.1]
    
    with patch("builtins.open", mock_open(read_data="Context")):
        result = pipeline.reprocess_article("hash123")
        
        assert result["status"] == "imported"
        assert result["metadata"]["relevance_score"] == 9
        
        # Verify history log
        mock_deps["HistoryManager"].return_value.log_change.assert_called_once()

def test_reprocess_article_not_found(pipeline, mock_deps):
    mock_db_instance = mock_deps["NewsDatabase"].return_value
    mock_db_instance.get_article.return_value = None
    
    result = pipeline.reprocess_article("missing")
    assert result["status"] == "error"
