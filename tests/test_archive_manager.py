import pytest
import os
import pandas as pd
from src.archive_manager import ArchiveManager
from datetime import datetime

@pytest.fixture
def archive_manager(tmp_path):
    return ArchiveManager(archive_dir=str(tmp_path))

def test_save_and_get_article(archive_manager):
    article = {
        "url": "http://example.com/1",
        "title": "Test Article 1",
        "published": "2023-10-01T12:00:00",
        "content": "Content 1"
    }
    
    archive_manager.save_articles([article])
    
    # Retrieve it
    retrieved = archive_manager.get_article("http://example.com/1", "2023-10-01")
    assert retrieved is not None
    assert retrieved["title"] == "Test Article 1"
    assert retrieved["url"] == "http://example.com/1"

def test_save_articles_updates_existing(archive_manager):
    article1 = {
        "url": "http://example.com/1",
        "title": "Test Article 1",
        "published": "2023-10-01T12:00:00",
        "content": "Content 1"
    }
    archive_manager.save_articles([article1])
    
    article2 = {
        "url": "http://example.com/1",
        "title": "Test Article 1 Updated",
        "published": "2023-10-01T12:00:00",
        "content": "Content 1 Updated"
    }
    archive_manager.save_articles([article2])
    
    retrieved = archive_manager.get_article("http://example.com/1", "2023-10-01")
    assert retrieved["title"] == "Test Article 1 Updated"
    assert retrieved["content"] == "Content 1 Updated"

def test_get_recent_articles(archive_manager):
    # Create articles in different months
    articles = [
        {
            "url": "http://example.com/1",
            "published": "2023-10-01T12:00:00",
            "title": "Oct Article"
        },
        {
            "url": "http://example.com/2",
            "published": "2023-11-01T12:00:00",
            "title": "Nov Article"
        }
    ]
    archive_manager.save_articles(articles)
    
    recent = archive_manager.get_recent_articles(limit=10)
    assert len(recent) == 2
    # Should be sorted by newest first (Nov then Oct) based on folder sort order in get_recent_articles
    # Note: get_recent_articles sorts folders reverse=True, so Nov (2023-11) comes before Oct (2023-10)
    # Inside folder, it takes tail, then reverses. 
    # Since we saved separately, they are in different folders.
    
    titles = [r["title"] for r in recent]
    assert "Nov Article" in titles
    assert "Oct Article" in titles

def test_get_article_no_date_fallback(archive_manager):
    # This relies on the fallback to current month if no date is provided
    # We'll save an article with current date
    now = datetime.now()
    article = {
        "url": "http://example.com/now",
        "title": "Now Article",
        "published": now.isoformat()
    }
    archive_manager.save_articles([article])
    
    # Try get without date
    retrieved = archive_manager.get_article("http://example.com/now")
    assert retrieved is not None
    assert retrieved["title"] == "Now Article"

def test_get_article_not_found(archive_manager):
    retrieved = archive_manager.get_article("http://nonexistent.com")
    assert retrieved is None
