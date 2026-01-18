import pytest
from unittest.mock import MagicMock, patch, mock_open
import feedparser
from src.aggregator.rss_scraper import RSSNewsAggregator

@pytest.fixture
def mock_archive_manager():
    with patch("src.aggregator.rss_scraper.ArchiveManager") as MockAM:
        yield MockAM.return_value

@pytest.fixture
def aggregator(mock_archive_manager, tmp_path):
    # Pass a temp cache dir
    return RSSNewsAggregator(feed_urls=["http://feed.com/rss"], cache_dir=str(tmp_path))

def test_fetch_feed_success(aggregator):
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.content = b"<rss>...</rss>"
        mock_get.return_value = mock_response
        
        with patch("feedparser.parse") as mock_parse:
            mock_parse.return_value = feedparser.FeedParserDict({"entries": []})
            
            feed, error = aggregator._fetch_feed("http://feed.com/rss")
            
            assert feed is not None
            assert error == ""
            mock_get.assert_called_once()
            mock_parse.assert_called_once()

def test_fetch_feed_network_error(aggregator):
    with patch("requests.get") as mock_get:
        mock_get.side_effect = Exception("Network Down")
        
        feed, error = aggregator._fetch_feed("http://feed.com/rss")
        
        assert feed is None
        assert "Network Down" in error

@patch("src.aggregator.rss_scraper.RSSNewsAggregator._scrape_article_content")
@patch("src.aggregator.rss_scraper.RSSNewsAggregator._fetch_feed")
def test_fetch_recent_articles(mock_fetch_feed, mock_scrape, aggregator):
    # Setup mock feed
    mock_entry = MagicMock()
    mock_entry.title = "Test Article"
    mock_entry.link = "http://test.com/article"
    mock_entry.published = "Mon, 01 Oct 2023 12:00:00 +0000"
    mock_entry.summary = "Summary"
    
    mock_feed = feedparser.FeedParserDict({
        "feed": {"title": "Test Feed"},
        "entries": [mock_entry]
    })
    mock_fetch_feed.return_value = (mock_feed, "")
    
    # Setup mock scrape
    mock_scrape.return_value = "Scraped Content"
    
    articles = aggregator.fetch_recent_articles(limit_per_feed=1)
    
    assert len(articles) == 1
    assert articles[0]["title"] == "Test Article"
    assert articles[0]["content"] == "Scraped Content"
    assert articles[0]["source"] == "Test Feed"
    
    # Verify archive was called
    aggregator.archive_manager.save_articles.assert_called_once()

@patch("src.aggregator.rss_scraper.RSSNewsAggregator._fetch_feed")
def test_fetch_recent_articles_skip_callback(mock_fetch_feed, aggregator):
    mock_entry = MagicMock()
    mock_entry.link = "http://test.com/skip"
    
    mock_feed = feedparser.FeedParserDict({
        "feed": {"title": "Test Feed"},
        "entries": [mock_entry]
    })
    mock_fetch_feed.return_value = (mock_feed, "")
    
    skip_cb = MagicMock(return_value=True)
    
    articles = aggregator.fetch_recent_articles(limit_per_feed=1, skip_callback=skip_cb)
    
    assert len(articles) == 0
    skip_cb.assert_called_with("http://test.com/skip")

def test_clean_summary(aggregator):
    raw = "<p>Summary text</p> <a href='#'>Continue reading...</a>"
    clean = aggregator._clean_summary(raw)
    assert clean == "Summary text"

@patch("requests.get")
def test_scrape_article_content_basic(mock_get, aggregator):
    html_content = """
    <html>
        <body>
            <p>Paragraph 1. This is a long enough paragraph to pass the length check which requires at least 200 characters to be considered a valid article content.</p>
            <p>Paragraph 2. We need to add more text here to ensure we definitely cross the threshold. The scraper has a heuristic to ignore very short content like cookie warnings or error messages.</p>
            <p>Paragraph 3. Adding a bit more text just to be safe and sound. The quick brown fox jumps over the lazy dog repeatedly until the buffer is full.</p>
        </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.content = html_content.encode("utf-8")
    mock_get.return_value = mock_response
    
    # Ensure archive miss
    aggregator.archive_manager.get_article.return_value = None
    
    content = aggregator._scrape_article_content("http://test.com/article")
    
    # It joins paragraphs
    assert "Paragraph 1." in content
    assert "Paragraph 2." in content

@patch("requests.get")
def test_scrape_article_content_archive_hit(mock_get, aggregator):
    # Setup archive hit
    aggregator.archive_manager.get_article.return_value = {"content": "Archived Content"}
    
    content = aggregator._scrape_article_content("http://test.com/article")
    
    assert content == "Archived Content"
    mock_get.assert_not_called()

def test_scrape_article_content_short_content(aggregator):
    # Mock requests to return very short content
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.content = b"<html><body><p>Too short.</p></body></html>"
        mock_get.return_value = mock_response
        
        aggregator.archive_manager.get_article.return_value = None
        
        content = aggregator._scrape_article_content("http://test.com/short")
        
        # Should return empty string if length < 200 (as per implementation)
        assert content == ""
