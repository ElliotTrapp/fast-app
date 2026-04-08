"""Knowledge base manager using SQLite."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class KnowledgeBase:
    """Manages persistent knowledge base in SQLite."""

    # Decay rates by fact type (for confidence calculation)
    DECAY_RATES = {
        "skill": 0.998,  # ~180 day half-life
        "experience": 0.996,  # ~120 day half-life
        "achievement": 0.997,  # ~150 day half-life
        "preference": 0.990,  # ~70 day half-life
        "general": 0.995,  # ~140 day half-life
    }

    def __init__(self, db_path: Path | str | None = None):
        """Initialize knowledge base.

        Args:
            db_path: Path to SQLite database file. If None, uses default location.
        """
        if db_path is None:
            db_path = Path.home() / ".fast_app" / "knowledge.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database with schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check if tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='facts'
            """)

            if not cursor.fetchone():
                # Create schema
                cursor.executescript(self._get_schema())
                conn.commit()

    def _get_schema(self) -> str:
        """Return SQL schema."""
        return """
        -- Facts: Atomic pieces of knowledge
        CREATE TABLE facts (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('skill', 'experience', 'achievement', 'preference', 'general')),
            confidence REAL DEFAULT 0.8 CHECK(confidence >= 0 AND confidence <= 1),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_confirmed TEXT NOT NULL DEFAULT (datetime('now')),
            source TEXT DEFAULT 'qa' CHECK(source IN ('qa', 'profile', 'imported', 'inferred')),
            version INTEGER DEFAULT 1,
            supersedes TEXT,
            job_url TEXT,
            question TEXT,
            metadata TEXT,
            FOREIGN KEY (supersedes) REFERENCES facts(id) ON DELETE SET NULL
        );

        CREATE INDEX idx_facts_type ON facts(type);
        CREATE INDEX idx_facts_confidence ON facts(confidence);
        CREATE INDEX idx_facts_last_confirmed ON facts(last_confirmed);
        CREATE INDEX idx_facts_source ON facts(source);
        CREATE INDEX idx_facts_type_confidence ON facts(type, confidence);

        -- Generations: Track each resume/cover letter generation
        CREATE TABLE generations (
            id TEXT PRIMARY KEY,
            job_url TEXT NOT NULL,
            job_title TEXT,
            company TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            rating INTEGER CHECK(rating >= 1 AND rating <= 5),
            feedback TEXT,
            outcome TEXT CHECK(outcome IN ('success', 'failure', 'pending'))
        );

        CREATE INDEX idx_generations_created ON generations(created_at);
        CREATE INDEX idx_generations_rating ON generations(rating);
        CREATE INDEX idx_generations_outcome ON generations(outcome);

        -- Fact Usage: Link facts to generations
        CREATE TABLE fact_usage (
            generation_id TEXT NOT NULL,
            fact_id TEXT NOT NULL,
            PRIMARY KEY (generation_id, fact_id),
            FOREIGN KEY (generation_id) REFERENCES generations(id) ON DELETE CASCADE,
            FOREIGN KEY (fact_id) REFERENCES facts(id) ON DELETE CASCADE
        );

        CREATE INDEX idx_fact_usage_generation ON fact_usage(generation_id);
        CREATE INDEX idx_fact_usage_fact ON fact_usage(fact_id);

        -- Patterns: Success/failure patterns
        CREATE TABLE patterns (
            id TEXT PRIMARY KEY,
            generation_id TEXT,
            pattern_type TEXT NOT NULL CHECK(pattern_type IN ('success', 'failure')),
            pattern_text TEXT NOT NULL,
            keywords TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (generation_id) REFERENCES generations(id) ON DELETE SET NULL
        );

        CREATE INDEX idx_patterns_type ON patterns(pattern_type);

        -- Metadata: KB state
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT INTO metadata (key, value) VALUES 
            ('version', '1.0.0'),
            ('created_at', datetime('now')),
            ('last_updated', datetime('now')),
            ('total_facts', '0'),
            ('total_generations', '0');
        """

    # ========================================================================
    # Fact Management (CRUD)
    # ========================================================================

    def add_fact(
        self,
        text: str,
        fact_type: str = "general",
        confidence: float = 0.8,
        source: str = "qa",
        job_url: str | None = None,
        question: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a fact to knowledge base.

        Args:
            text: The fact text (atomic, self-contained)
            fact_type: Type of fact (skill/experience/achievement/preference/general)
            confidence: Initial confidence (0.0-1.0)
            source: Where this fact came from
            job_url: URL of the job this fact relates to
            question: The question that elicited this fact
            metadata: Additional metadata as JSON

        Returns:
            Fact ID
        """
        fact_id = str(uuid4())
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check for similar facts (potential duplicate)
            cursor.execute(
                "SELECT id, text, version FROM facts WHERE text = ? AND type = ?", (text, fact_type)
            )
            existing = cursor.fetchone()

            if existing:
                # Create new version that supersedes the old one
                fact_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO facts (id, text, type, confidence, source, version, supersedes, job_url, question, metadata, created_at, last_confirmed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact_id,
                        text,
                        fact_type,
                        confidence,
                        source,
                        existing[2] + 1,  # Increment version
                        existing[0],  # Supersede old fact
                        job_url,
                        question,
                        json.dumps(metadata) if metadata else None,
                        now,
                        now,
                    ),
                )
            else:
                # Insert new fact
                cursor.execute(
                    """
                    INSERT INTO facts (id, text, type, confidence, source, job_url, question, metadata, created_at, last_confirmed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact_id,
                        text,
                        fact_type,
                        confidence,
                        source,
                        job_url,
                        question,
                        json.dumps(metadata) if metadata else None,
                        now,
                        now,
                    ),
                )

            # Update metadata
            cursor.execute(
                "UPDATE metadata SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'total_facts'"
            )
            cursor.execute("UPDATE metadata SET value = ? WHERE key = 'last_updated'", (now,))
            conn.commit()

        return fact_id

    def get_fact(self, fact_id: str) -> dict[str, Any] | None:
        """Get fact by ID.

        Args:
            fact_id: Fact ID

        Returns:
            Fact as dictionary or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM facts WHERE id = ?", (fact_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    def search_facts(
        self,
        query: str | None = None,
        fact_type: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search facts with filters.

        Args:
            query: Text to search for (LIKE query)
            fact_type: Filter by type
            min_confidence: Minimum confidence threshold
            limit: Maximum results to return
            offset: Offset for pagination

        Returns:
            List of facts as dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build query
            conditions = []
            params = []

            if query:
                conditions.append("text LIKE ?")
                params.append(f"%{query}%")

            if fact_type:
                conditions.append("type = ?")
                params.append(fact_type)

            conditions.append("confidence >= ?")
            params.append(min_confidence)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor.execute(
                f"""
                SELECT * FROM facts
                WHERE {where_clause}
                ORDER BY last_confirmed DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def update_fact(self, fact_id: str, **kwargs) -> bool:
        """Update fact fields.

        Args:
            fact_id: Fact ID
            **kwargs: Fields to update (text, confidence, metadata, last_confirmed, etc.)

        Returns:
            True if updated, False if fact not found
        """
        allowed_fields = {
            "text",
            "type",
            "confidence",
            "source",
            "job_url",
            "question",
            "metadata",
            "last_confirmed",
        }
        update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not update_fields:
            return False

        # Build UPDATE query
        set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
        params = list(update_fields.values()) + [fact_id]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE facts SET {set_clause} WHERE id = ?", params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_fact(self, fact_id: str) -> bool:
        """Delete a fact.

        Args:
            fact_id: Fact ID

        Returns:
            True if deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ========================================================================
    # Confidence & Staleness
    # ========================================================================

    def get_current_confidence(self, fact_id: str) -> float:
        """Calculate current confidence with time decay.

        Args:
            fact_id: Fact ID

        Returns:
            Current confidence (0.0-1.0)
        """
        fact = self.get_fact(fact_id)
        if not fact:
            return 0.0

        # Parse timestamp
        last_confirmed = datetime.fromisoformat(fact["last_confirmed"])
        days_old = (datetime.now() - last_confirmed).days

        # Get decay rate for fact type
        decay_rate = self.DECAY_RATES.get(fact["type"], 0.995)

        # Calculate current confidence
        current_confidence = fact["confidence"] * (decay_rate**days_old)

        return max(0.0, min(1.0, current_confidence))

    def get_facts_needing_refresh(self, threshold: float = 0.6) -> list[dict[str, Any]]:
        """Get facts with low confidence that need user confirmation.

        Args:
            threshold: Confidence threshold (facts below this need refresh)

        Returns:
            List of stale facts with current confidence
        """
        facts = self.search_facts(limit=1000)

        needs_refresh = []
        for fact in facts:
            current_conf = self.get_current_confidence(fact["id"])
            if current_conf < threshold:
                fact["current_confidence"] = current_conf

                # Calculate age
                last_confirmed = datetime.fromisoformat(fact["last_confirmed"])
                fact["days_old"] = (datetime.now() - last_confirmed).days

                needs_refresh.append(fact)

        # Sort by confidence (lowest first)
        return sorted(needs_refresh, key=lambda x: x["current_confidence"])

    def refresh_fact(
        self, fact_id: str, confirmed: bool = True, updated_text: str | None = None
    ) -> bool:
        """Mark fact as confirmed (refresh confidence).

        Args:
            fact_id: Fact ID
            confirmed: Whether user confirmed this fact is still accurate
            updated_text: New text if user updated it

        Returns:
            True if refreshed, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if updated_text:
                cursor.execute(
                    "UPDATE facts SET text = ?, last_confirmed = datetime('now') WHERE id = ?",
                    (updated_text, fact_id),
                )
            else:
                cursor.execute(
                    "UPDATE facts SET last_confirmed = datetime('now') WHERE id = ?", (fact_id,)
                )

            if not confirmed:
                # Lower confidence if user says it's wrong
                cursor.execute(
                    "UPDATE facts SET confidence = MIN(confidence * 0.5, 0.3) WHERE id = ?",
                    (fact_id,),
                )

            # Update metadata
            cursor.execute("UPDATE metadata SET value = datetime('now') WHERE key = 'last_updated'")
            conn.commit()
            return cursor.rowcount > 0

    # ========================================================================
    # Generation Tracking
    # ========================================================================

    def record_generation(
        self,
        job_url: str,
        job_title: str | None = None,
        company: str | None = None,
        facts_used: list[str] | None = None,
    ) -> str:
        """Record a resume/cover letter generation.

        Args:
            job_url: Job URL
            job_title: Job title
            company: Company name
            facts_used: List of fact IDs used in generation

        Returns:
            Generation ID
        """
        generation_id = str(uuid4())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Insert generation
            cursor.execute(
                """
                INSERT INTO generations (id, job_url, job_title, company)
                VALUES (?, ?, ?, ?)
                """,
                (generation_id, job_url, job_title, company),
            )

            # Link facts used
            if facts_used:
                for fact_id in facts_used:
                    cursor.execute(
                        """
                        INSERT INTO fact_usage (generation_id, fact_id)
                        VALUES (?, ?)
                        """,
                        (generation_id, fact_id),
                    )

            # Update metadata
            cursor.execute(
                "UPDATE metadata SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'total_generations'"
            )
            cursor.execute("UPDATE metadata SET value = datetime('now') WHERE key = 'last_updated'")
            conn.commit()

        return generation_id

    def record_feedback(
        self,
        generation_id: str,
        rating: int,
        feedback: str | None = None,
    ) -> bool:
        """Record user feedback on a generation.

        Args:
            generation_id: Generation ID
            rating: Rating (1-5)
            feedback: Optional feedback text

        Returns:
            True if recorded, False if generation not found
        """
        # Determine outcome based on rating
        if rating >= 4:
            outcome = "success"
        elif rating <= 2:
            outcome = "failure"
        else:
            outcome = "pending"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE generations
                SET rating = ?, feedback = ?, outcome = ?
                WHERE id = ?
                """,
                (rating, feedback, outcome, generation_id),
            )

            conn.commit()
            return cursor.rowcount > 0

    def get_generation(self, generation_id: str) -> dict[str, Any] | None:
        """Get generation by ID.

        Args:
            generation_id: Generation ID

        Returns:
            Generation as dictionary or None
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM generations WHERE id = ?", (generation_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    def get_recent_generations(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent generations.

        Args:
            limit: Maximum results

        Returns:
            List of generations
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM generations
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # ========================================================================
    # Pattern Extraction
    # ========================================================================

    def add_pattern(
        self,
        pattern_type: str,
        pattern_text: str,
        keywords: list[str] | None = None,
        generation_id: str | None = None,
    ) -> str:
        """Add a success/failure pattern.

        Args:
            pattern_type: 'success' or 'failure'
            pattern_text: Human-readable pattern description
            keywords: Keywords for matching
            generation_id: Which generation this came from

        Returns:
            Pattern ID
        """
        pattern_id = str(uuid4())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO patterns (id, generation_id, pattern_type, pattern_text, keywords)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    pattern_id,
                    generation_id,
                    pattern_type,
                    pattern_text,
                    json.dumps(keywords) if keywords else None,
                ),
            )

            conn.commit()

        return pattern_id

    def get_patterns_by_type(self, pattern_type: str | None = None) -> list[dict[str, Any]]:
        """Get patterns by type.

        Args:
            pattern_type: 'success', 'failure', or None for all

        Returns:
            List of patterns
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if pattern_type:
                cursor.execute(
                    "SELECT * FROM patterns WHERE pattern_type = ? ORDER BY created_at DESC",
                    (pattern_type,),
                )
            else:
                cursor.execute("SELECT * FROM patterns ORDER BY created_at DESC")

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics.

        Returns:
            Dictionary of statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            stats = {}

            # Total facts
            cursor.execute("SELECT COUNT(*) FROM facts")
            stats["total_facts"] = cursor.fetchone()[0]

            # Facts by type
            cursor.execute("SELECT type, COUNT(*) FROM facts GROUP BY type")
            stats["facts_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

            # Facts by source
            cursor.execute("SELECT source, COUNT(*) FROM facts GROUP BY source")
            stats["facts_by_source"] = {row[0]: row[1] for row in cursor.fetchall()}

            # Average confidence
            cursor.execute("SELECT AVG(confidence) FROM facts")
            stats["avg_confidence"] = cursor.fetchone()[0] or 0.0

            # Total generations
            cursor.execute("SELECT COUNT(*) FROM generations")
            stats["total_generations"] = cursor.fetchone()[0]

            # Generations by outcome
            cursor.execute("""
                SELECT outcome, COUNT(*) 
                FROM generations 
                WHERE outcome IS NOT NULL
                GROUP BY outcome
            """)
            stats["generations_by_outcome"] = {row[0]: row[1] for row in cursor.fetchall()}

            # Successful/failed generations
            outcomes = stats["generations_by_outcome"]
            stats["successful_generations"] = outcomes.get("success", 0)
            stats["failed_generations"] = outcomes.get("failure", 0)

            # Average rating
            cursor.execute("SELECT AVG(rating) FROM generations WHERE rating IS NOT NULL")
            stats["avg_rating"] = cursor.fetchone()[0] or 0.0

            # Total patterns
            cursor.execute("SELECT COUNT(*) FROM patterns")
            stats["total_patterns"] = cursor.fetchone()[0]

            # Facts needing refresh
            stats["facts_needing_refresh"] = len(self.get_facts_needing_refresh())

            # Metadata
            cursor.execute("SELECT key, value FROM metadata")
            stats["metadata"] = {row[0]: row[1] for row in cursor.fetchall()}

            return stats

    # ========================================================================
    # Import/Export
    # ========================================================================

    def export_to_json(self) -> dict[str, Any]:
        """Export entire KB to JSON for backup.

        Returns:
            Dictionary containing all KB data
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all facts
            cursor.execute("SELECT * FROM facts ORDER BY created_at")
            facts = [dict(row) for row in cursor.fetchall()]

            # Get all generations
            cursor.execute("SELECT * FROM generations ORDER BY created_at")
            generations = [dict(row) for row in cursor.fetchall()]

            # Get all fact_usage
            cursor.execute("SELECT * FROM fact_usage")
            fact_usage = [dict(row) for row in cursor.fetchall()]

            # Get all patterns
            cursor.execute("SELECT * FROM patterns ORDER BY created_at")
            patterns = [dict(row) for row in cursor.fetchall()]

            # Get metadata
            cursor.execute("SELECT key, value FROM metadata")
            metadata = {row[0]: row[1] for row in cursor.fetchall()}

            return {
                "facts": facts,
                "generations": generations,
                "fact_usage": fact_usage,
                "patterns": patterns,
                "metadata": metadata,
                "exported_at": datetime.now().isoformat(),
            }

    def import_from_json(self, data: dict[str, Any]):
        """Import KB from JSON backup.

        Args:
            data: Dictionary containing KB data
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Clear existing data
            cursor.execute("DELETE FROM fact_usage")
            cursor.execute("DELETE FROM patterns")
            cursor.execute("DELETE FROM generations")
            cursor.execute("DELETE FROM facts")

            # Import facts
            for fact in data.get("facts", []):
                # Generate ID and timestamps if not provided
                fact_id = fact.get("id", str(uuid4()))
                created_at = fact.get("created_at", datetime.now().isoformat())
                last_confirmed = fact.get("last_confirmed", created_at)
                confidence = fact.get("confidence", 0.8)
                version = fact.get("version", 1)

                cursor.execute(
                    """
                    INSERT INTO facts (id, text, type, confidence, created_at, last_confirmed, source, version, supersedes, job_url, question, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact_id,
                        fact["text"],
                        fact["type"],
                        confidence,
                        created_at,
                        last_confirmed,
                        fact["source"],
                        version,
                        fact.get("supersedes"),
                        fact.get("job_url"),
                        fact.get("question"),
                        fact.get("metadata"),
                    ),
                )

            # Import generations
            for gen in data.get("generations", []):
                cursor.execute(
                    """
                    INSERT INTO generations (id, job_url, job_title, company, created_at, rating, feedback, outcome)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        gen["id"],
                        gen["job_url"],
                        gen.get("job_title"),
                        gen.get("company"),
                        gen["created_at"],
                        gen.get("rating"),
                        gen.get("feedback"),
                        gen.get("outcome"),
                    ),
                )

            # Import fact_usage
            for usage in data.get("fact_usage", []):
                cursor.execute(
                    "INSERT INTO fact_usage (generation_id, fact_id) VALUES (?, ?)",
                    (usage["generation_id"], usage["fact_id"]),
                )

            # Import patterns
            for pattern in data.get("patterns", []):
                cursor.execute(
                    """
                    INSERT INTO patterns (id, generation_id, pattern_type, pattern_text, keywords, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pattern["id"],
                        pattern.get("generation_id"),
                        pattern["pattern_type"],
                        pattern["pattern_text"],
                        pattern.get("keywords"),
                        pattern["created_at"],
                    ),
                )

            # Update metadata
            cursor.execute(
                "UPDATE metadata SET value = ? WHERE key = 'last_updated'",
                (datetime.now().isoformat(),),
            )

            conn.commit()
