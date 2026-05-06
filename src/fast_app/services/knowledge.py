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
from ..models.knowledge import (
    ExtractedFact,
    FactCreate,
    FactUpdate,
    KnowledgeSearchResult,
)


class KnowledgeService:
    """Manages per-user knowledge storage and retrieval via ChromaDB.

    This service handles:
    - Storing extracted facts with metadata (category, confidence, source)
    - Semantic search across a user's knowledge base
    - Listing and deleting facts
    - Graceful degradation when ChromaDB is unavailable

    ChromaDB PersistentClient instances are cached at the class level so that
    all KnowledgeService objects sharing the same database path reuse the same
    client.  This avoids stale-cache bugs where a deletion performed through one
    client is not visible to a different client that still holds an in-memory
    snapshot of the old data.

    Attributes:
        config: Application configuration containing ChromaConfig.
        _client: ChromaDB client instance (PersistentClient or HttpClient).
        _embedding_model: LangChain embedding model for vector operations.
    """

    # Class-level cache: (db_path_or_url, client_type) → chromadb client
    # Ensures a single PersistentClient per on-disk database, which prevents
    # the "delete doesn't persist" bug caused by per-request client creation.
    _client_cache: dict[tuple[str, str], Any] = {}

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

    @classmethod
    def reset_client_cache(cls) -> None:
        """Clear the class-level ChromaDB client cache.

        Primarily useful in tests to avoid state leaking between test cases.
        """
        cls._client_cache.clear()

    def _init_chromadb(self) -> None:
        """Initialize the ChromaDB client and embedding model.

        Uses PersistentClient for local development and HttpClient for
        production ChromaDB server.  Client instances are cached at the
        class level so that all KnowledgeService objects sharing the same
        database path reuse the same client, preventing stale-cache bugs.
        """
        import chromadb

        if self.config.chroma.client_type == "http":
            cache_key = (
                f"http://{self.config.chroma.host}:{self.config.chroma.port}",
                "http",
            )
            if cache_key not in KnowledgeService._client_cache:
                KnowledgeService._client_cache[cache_key] = chromadb.HttpClient(
                    host=self.config.chroma.host,
                    port=self.config.chroma.port,
                )
            self._client = KnowledgeService._client_cache[cache_key]
        else:
            from pathlib import Path

            db_path = self.config.chroma.path or str(Path.home() / ".fast-app" / "chroma")
            cache_key = (db_path, "persistent")
            if cache_key not in KnowledgeService._client_cache:
                Path(db_path).mkdir(parents=True, exist_ok=True)
                KnowledgeService._client_cache[cache_key] = chromadb.PersistentClient(path=db_path)
            self._client = KnowledgeService._client_cache[cache_key]

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
        and filtering. Facts with duplicate content (case-insensitive exact
        match) are skipped to prevent redundant entries.

        Args:
            facts: List of ExtractedFact objects from the fact extraction pipeline.
            job_url: Optional URL of the job posting that triggered this extraction.
            source: Source of the facts (e.g., "qa_session", "manual_entry").

        Returns:
            List of fact IDs that were stored (excludes duplicates).
        """
        collection = self._get_or_create_collection()
        if collection is None:
            logger.warning("ChromaDB unavailable; facts not stored")
            return []

        existing_contents = set()
        if collection.count() > 0:
            existing = collection.get(include=["documents"])
            existing_contents = {doc.lower().strip() for doc in existing["documents"]}

        ids = []
        documents = []
        metadatas = []
        skipped = 0

        for fact in facts:
            normalized = fact.content.lower().strip()
            if normalized in existing_contents:
                skipped += 1
                continue
            existing_contents.add(normalized)

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

        if ids:
            collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(
            f"Stored {len(ids)} facts in {self._collection_name} (skipped {skipped} duplicates)"
        )

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

    def add_fact(self, user_id: int, fact: FactCreate) -> dict[str, Any]:
        """Add a single fact to the user's knowledge collection.

        If a fact with identical content (case-insensitive) already exists,
        the duplicate is skipped and an empty dict is returned.

        Args:
            user_id: The user ID (used for collection isolation).
            fact: FactCreate schema with content, category, source, job_url, confidence.

        Returns:
            Dict with id, content, category, source, job_url, confidence, created_at.
            Empty dict if ChromaDB is unavailable or fact is a duplicate.
        """
        collection = self._get_or_create_collection()
        if collection is None:
            logger.warning("ChromaDB unavailable; fact not added")
            return {}

        normalized = fact.content.lower().strip()
        if collection.count() > 0:
            existing = collection.get(include=["documents"])
            existing_contents = {doc.lower().strip() for doc in existing["documents"]}
            if normalized in existing_contents:
                logger.info(
                    f"Skipping duplicate fact in {self._collection_name}: {fact.content[:50]}"
                )
                return {"duplicate": True, "content": fact.content}

        fact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "category": fact.category,
            "source": fact.source or "manual_entry",
            "confidence": fact.confidence,
            "job_url": fact.job_url or "",
            "extracted_at": now,
        }

        collection.add(
            ids=[fact_id],
            documents=[fact.content],
            metadatas=[metadata],
        )
        logger.info(f"Added fact {fact_id} to {self._collection_name}")

        return {
            "id": fact_id,
            "content": fact.content,
            "category": fact.category,
            "source": fact.source or "manual_entry",
            "job_url": fact.job_url or "",
            "confidence": fact.confidence,
            "created_at": now,
        }

    def update_fact(self, user_id: int, fact_id: str, fact: FactUpdate) -> dict[str, Any] | None:
        """Update an existing fact by deleting and re-inserting.

        ChromaDB has no native update, so we delete the old fact and insert
        a new one with updated fields. The UUID changes on update.

        Args:
            user_id: The user ID (used for collection isolation).
            fact_id: The ID of the fact to update.
            fact: FactUpdate schema with optional fields to update.

        Returns:
            Updated fact dict, or None if the fact was not found.
        """
        collection = self._get_or_create_collection()
        if collection is None:
            logger.warning("ChromaDB unavailable; fact not updated")
            return None

        # Retrieve the existing fact
        try:
            results = collection.get(ids=[fact_id])
        except Exception:
            return None

        if not results["ids"]:
            return None

        # Extract existing values
        old_content = results["documents"][0]
        old_metadata = results["metadatas"][0]

        # Merge updates
        new_content = fact.content if fact.content is not None else old_content
        new_category = (
            fact.category if fact.category is not None else old_metadata.get("category", "general")
        )
        new_source = (
            fact.source if fact.source is not None else old_metadata.get("source", "manual_entry")
        )
        new_confidence = (
            fact.confidence if fact.confidence is not None else old_metadata.get("confidence", 1.0)
        )
        old_job_url = old_metadata.get("job_url", "")

        # Delete old fact and insert new one
        collection.delete(ids=[fact_id])

        new_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        new_metadata = {
            "category": new_category,
            "source": new_source,
            "confidence": new_confidence,
            "job_url": old_job_url,
            "extracted_at": now,
        }

        collection.add(
            ids=[new_id],
            documents=[new_content],
            metadatas=[new_metadata],
        )
        logger.info(f"Updated fact {fact_id} → {new_id} in {self._collection_name}")

        return {
            "id": new_id,
            "content": new_content,
            "category": new_category,
            "source": new_source,
            "job_url": old_job_url,
            "confidence": new_confidence,
            "created_at": now,
        }

    def delete_all_facts(self) -> int:
        """Delete all facts in the user's knowledge collection.

        Removes every document from the user's ChromaDB collection.
        Used when a user wants to start fresh (e.g., after importing a new profile).

        Args:
            None — operates on the collection identified by self._collection_name.

        Returns:
            The number of facts that were deleted. Returns 0 if the collection
            is empty or ChromaDB is unavailable.
        """
        collection = self._get_or_create_collection()
        if collection is None:
            logger.warning("ChromaDB unavailable; no facts deleted")
            return 0

        count = collection.count()
        if count == 0:
            return 0

        results = collection.get()
        ids = results["ids"]
        if ids:
            collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} facts from {self._collection_name}")

        return len(ids)

    def get_categories(self, user_id: int) -> list[str]:
        """Get unique categories from the user's knowledge collection.

        Args:
            user_id: The user ID (used for collection isolation).

        Returns:
            Sorted list of unique category strings.
        """
        collection = self._get_or_create_collection()
        if collection is None:
            return []

        if collection.count() == 0:
            return []

        results = collection.get(include=["metadatas"])
        categories = set()
        for metadata in results["metadatas"]:
            cat = metadata.get("category", "")
            if cat:
                categories.add(cat)

        return sorted(categories)
