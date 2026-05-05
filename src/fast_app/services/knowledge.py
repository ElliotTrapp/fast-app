"""Knowledge service for storing and retrieving learned facts via ChromaDB.

This module provides the KnowledgeService class, which manages per-user vector
collections in ChromaDB. It handles storing extracted facts, semantic search,
and fact management (list, delete).

## Architecture

    User answers questions
          │
          ▼
    FactExtractor.extract_facts_from_answers()
          │  (LangChain chain → LLM → FactExtractionResult)
          ▼
    KnowledgeService.store_facts()
          │  (embed each fact → store in ChromaDB with metadata)
          ▼
    ChromaDB collection: user_{id}_knowledge

    Future session:
          │
          ▼
    KnowledgeService.query_facts()
          │  (embed query → search ChromaDB)
          ▼
    Inject retrieved facts into question generation prompt

## Per-User Collections

Each user has a separate ChromaDB collection:
    "user_1_knowledge" → facts for user with ID 1
    "user_2_knowledge" → facts for user with ID 2

This ensures complete isolation between users' knowledge bases.

## Graceful Degradation

If ChromaDB is not installed (missing [knowledge] dependency group), all
operations log a warning and return empty results. The system works identically
to how it does without knowledge features — just without memory-augmented prompts.

Use the --no-knowledge flag to explicitly disable knowledge features.

See: docs/adr/002-chromadb-vector-memory.md, docs/guide/knowledge.md
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..config import Config
from ..log import logger
from ..models.knowledge import ExtractedFact, KnowledgeSearchResult


class KnowledgeService:
    """Manages per-user knowledge storage and retrieval via ChromaDB.

    This service handles:
    - Storing extracted facts with metadata (category, confidence, source)
    - Semantic search across a user's knowledge base
    - Listing and deleting facts
    - Graceful degradation when ChromaDB is unavailable

    Attributes:
        config: Application configuration containing ChromaConfig.
        _client: ChromaDB client instance (PersistentClient or HttpClient).
        _embedding_model: LangChain embedding model for vector operations.
    """

    def __init__(self, config: Config, user_id: int | None = None):
        """Initialize the knowledge service.

        Args:
            config: Application config containing ChromaConfig.
            user_id: Optional user ID for per-user collection isolation.
                If None, uses a global "anonymous" collection.

        Raises:
            ImportError: If chromadb is not installed and config.chroma is set.
        """
        self.config = config
        self.user_id = user_id
        self._client = None
        self._embedding_model = None

        try:
            self._init_chromadb()
        except ImportError:
            logger.warning(
                "chromadb not installed; knowledge features disabled. "
                "Install with: pip install -e '.[knowledge]'"
            )

    def _init_chromadb(self) -> None:
        """Initialize the ChromaDB client and embedding model.

        Uses PersistentClient for local development and HttpClient for
        production ChromaDB server.
        """
        import chromadb

        if self.config.chroma.client_type == "http":
            self._client = chromadb.HttpClient(
                host=self.config.chroma.host,
                port=self.config.chroma.port,
            )
        else:
            from pathlib import Path

            db_path = self.config.chroma.path or str(Path.home() / ".fast-app" / "chroma")
            Path(db_path).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=db_path)

        self._init_embedding_model()

    def _init_embedding_model(self) -> None:
        """Initialize the embedding model based on LLM provider configuration.

        Uses OllamaEmbeddings for local providers and OpenAIEmbeddings for
        cloud providers.
        """
        provider = self.config.llm.provider

        if provider == "ollama":
            try:
                from langchain_ollama import OllamaEmbeddings

                self._embedding_model = OllamaEmbeddings(
                    model=self.config.chroma.embedding_model,
                    base_url=self.config.ollama.endpoint,
                )
            except ImportError:
                logger.warning("langchain-ollama not installed; using default embeddings")
        elif provider == "opencode-go":
            try:
                from langchain_openai import OpenAIEmbeddings

                self._embedding_model = OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    api_key=self.config.llm.api_key,
                    base_url=self.config.llm.base_url or "https://opencode.ai/zen/go/v1",
                )
            except ImportError:
                logger.warning("langchain-openai not installed; using default embeddings")

    @property
    def _collection_name(self) -> str:
        """Get the ChromaDB collection name for the current user."""
        if self.user_id:
            return f"user_{self.user_id}_knowledge"
        return "anonymous_knowledge"

    def _get_or_create_collection(self) -> Any:
        """Get or create the user's ChromaDB collection.

        Returns:
            ChromaDB collection instance, or None if ChromaDB is unavailable.
        """
        if self._client is None:
            return None

        return self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def store_facts(
        self,
        facts: list[ExtractedFact],
        job_url: str | None = None,
        source: str = "qa_session",
    ) -> list[str]:
        """Store extracted facts in the user's knowledge collection.

        Each fact is embedded and stored with rich metadata for later retrieval
        and filtering.

        Args:
            facts: List of ExtractedFact objects from the fact extraction pipeline.
            job_url: Optional URL of the job posting that triggered this extraction.
            source: Source of the facts (e.g., "qa_session", "manual_entry").

        Returns:
            List of fact IDs that were stored.
        """
        collection = self._get_or_create_collection()
        if collection is None:
            logger.warning("ChromaDB unavailable; facts not stored")
            return []

        ids = []
        documents = []
        metadatas = []

        for fact in facts:
            fact_id = str(uuid.uuid4())
            ids.append(fact_id)
            documents.append(fact.content)
            metadatas.append(
                {
                    "category": fact.category,
                    "source": source,
                    "confidence": fact.confidence,
                    "job_url": job_url or "",
                    "source_question": fact.source_question,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(f"Stored {len(facts)} facts in {self._collection_name}")

        return ids

    def query_facts(
        self,
        query: str,
        n: int = 5,
        category: str | None = None,
    ) -> list[KnowledgeSearchResult]:
        """Search for facts semantically related to a query.

        Args:
            query: Natural language query to search for.
            n: Number of results to return (default 5).
            category: Optional category filter (e.g., "skill", "experience").

        Returns:
            List of KnowledgeSearchResult objects ranked by relevance.
        """
        collection = self._get_or_create_collection()
        if collection is None:
            return []

        if collection.count() == 0:
            return []

        where_filter = None
        if category:
            where_filter = {"category": {"$eq": category}}

        results = collection.query(
            query_texts=[query],
            n_results=min(n, collection.count()),
            where=where_filter,
        )

        search_results = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i] if "distances" in results else None
            fact_id = results["ids"][0][i] if "ids" in results else ""
            search_results.append(
                KnowledgeSearchResult(
                    id=fact_id,
                    content=doc,
                    category=metadata.get("category", ""),
                    confidence=metadata.get("confidence", 0.0),
                    source=metadata.get("source", ""),
                    distance=distance,
                    metadata=metadata,
                )
            )

        return search_results

    def list_facts(
        self,
        limit: int = 100,
        category: str | None = None,
    ) -> list[KnowledgeSearchResult]:
        """List all facts in the user's knowledge collection.

        Args:
            limit: Maximum number of facts to return.
            category: Optional category filter.

        Returns:
            List of KnowledgeSearchResult objects.
        """
        collection = self._get_or_create_collection()
        if collection is None:
            return []

        if collection.count() == 0:
            return []

        where_filter = None
        if category:
            where_filter = {"category": {"$eq": category}}

        results = collection.get(
            limit=limit,
            where=where_filter,
        )

        facts = []
        for i, doc in enumerate(results["documents"]):
            metadata = results["metadatas"][i]
            fact_id = results["ids"][i] if "ids" in results else ""
            facts.append(
                KnowledgeSearchResult(
                    id=fact_id,
                    content=doc,
                    category=metadata.get("category", ""),
                    confidence=metadata.get("confidence", 0.0),
                    source=metadata.get("source", ""),
                    distance=None,
                    metadata=metadata,
                )
            )

        return facts

    def delete_facts(self, fact_ids: list[str]) -> bool:
        """Delete specific facts by their IDs.

        Args:
            fact_ids: List of fact IDs to delete.

        Returns:
            True if deletion was successful, False if ChromaDB is unavailable.
        """
        collection = self._get_or_create_collection()
        if collection is None:
            return False

        collection.delete(ids=fact_ids)
        logger.info(f"Deleted {len(fact_ids)} facts from {self._collection_name}")
        return True
