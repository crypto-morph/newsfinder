import chromadb
from chromadb.config import Settings
import logging
from typing import List, Dict, Optional
import os

logger = logging.getLogger(__name__)

class NewsDatabase:
    def __init__(self, persist_directory: str = "chroma_db"):
        """
        Initialize the ChromaDB client.
        """
        # Ensure directory exists
        os.makedirs(persist_directory, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # Get or create the collection
        self.collection = self.client.get_or_create_collection(
            name="news_articles",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Connected to ChromaDB at {persist_directory}, collection 'news_articles' ready.")

    def add_article(self, article_id: str, text: str, embedding: List[float], metadata: Dict):
        """
        Add an article to the database.
        """
        try:
            self.collection.add(
                ids=[article_id],
                documents=[text],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            logger.info(f"Added article {article_id} to database.")
        except Exception as e:
            logger.error(f"Error adding article {article_id}: {e}")

    def query_articles(self, query_embedding: List[float], n_results: int = 5) -> Dict:
        """
        Search for articles using a vector embedding.
        """
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )

    def article_exists(self, article_id: str) -> bool:
        """Check if an article already exists in the collection."""
        try:
            result = self.collection.get(ids=[article_id], include=[])
            return bool(result.get("ids"))
        except Exception:
            return False

    def get_stats(self):
        """
        Return count of items in collection.
        """
        return self.collection.count()

    def get_all_articles(self, limit: int = 1000) -> List[Dict]:
        """Return all articles in the database up to a limit."""
        data = self.collection.peek(limit=limit)
        if not data:
            return []

        ids = data.get("ids", [])
        documents = data.get("documents", [])
        metadatas = data.get("metadatas", [])

        articles: List[Dict] = []
        for idx, article_id in enumerate(ids):
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            summary = documents[idx] if idx < len(documents) else ""
            article = {"id": article_id, "summary_text": summary}
            article.update(metadata or {})
            articles.append(article)

        # Sort by published date desc if available
        # Note: published_date string format might vary, so this is best effort
        articles.sort(key=lambda x: x.get("published_date", ""), reverse=True)
        
        return articles

    def list_recent_articles(self, limit: int = 10) -> List[Dict]:
        """Peek into the collection and return recent articles with metadata."""
        data = self.collection.peek(limit=limit * 3)
        if not data:
            return []

        ids = data.get("ids", [])
        documents = data.get("documents", [])
        metadatas = data.get("metadatas", [])

        articles: List[Dict] = []
        seen_urls: set[str] = set()
        for idx, article_id in enumerate(ids):
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            summary = documents[idx] if idx < len(documents) else ""
            article = {"id": article_id, "summary_text": summary}
            article.update(metadata or {})
            url = article.get("url")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            articles.append(article)
            if len(articles) >= limit:
                break

        return articles

    def get_article(self, article_id: str) -> Optional[Dict]:
        """Fetch a single article with metadata and summary text."""
        try:
            data = self.collection.get(ids=[article_id], include=["documents", "metadatas"])
        except Exception as exc:
            logger.error("Error fetching article %s: %s", article_id, exc)
            return None

        if not data.get("ids"):
            return None

        metadata = data.get("metadatas", [{}])[0] or {}
        summary_text = data.get("documents", [""])[0] or ""
        article = {"id": article_id, "summary_text": summary_text}
        article.update(metadata)
        return article

    def update_article_metadata(self, article_id: str, metadata: Dict) -> bool:
        """Update metadata for an existing article."""
        try:
            self.collection.update(ids=[article_id], metadatas=[metadata])
            return True
        except Exception:
            try:
                existing = self.collection.get(
                    ids=[article_id], include=["documents", "embeddings", "metadatas"]
                )
                if not existing.get("ids"):
                    return False
                document = existing.get("documents", [""])[0]
                embedding = None
                if existing.get("embeddings"):
                    embedding = existing["embeddings"][0]
                current_meta = existing.get("metadatas", [{}])[0] or {}
                merged_meta = {**current_meta, **metadata}

                payload = {
                    "ids": [article_id],
                    "documents": [document],
                    "metadatas": [merged_meta],
                }
                if embedding is not None:
                    payload["embeddings"] = [embedding]
                self.collection.upsert(**payload)
                return True
            except Exception as exc:
                logger.error("Failed to update article metadata %s: %s", article_id, exc)
                return False

    def delete_article(self, article_id: str) -> bool:
        """Delete an article from the database by ID."""
        try:
            self.collection.delete(ids=[article_id])
            logger.info("Deleted article %s", article_id)
            return True
        except Exception as e:
            logger.error("Error deleting article %s: %s", article_id, e)
            return False
