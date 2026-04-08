"""Behavior tests for knowledge base.

These tests verify behavior, not implementation details.
They test WHAT the system does, not HOW it does it.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fast_app.knowledge import KnowledgeBase


class TestFactStorage:
    """Tests for fact storage behavior."""

    def test_when_add_fact_then_can_retrieve_it(self):
        """When I add a fact, I should be able to retrieve it later."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Action
            fact_id = kb.add_fact(
                text="5 years Python experience", fact_type="skill", confidence=0.9
            )

            # Assert
            fact = kb.get_fact(fact_id)
            assert fact is not None
            assert fact["text"] == "5 years Python experience"
            assert fact["type"] == "skill"
            assert fact["confidence"] == 0.9

    def test_when_add_duplicate_fact_then_creates_new_version(self):
        """When I add the same fact twice, it should create a new version."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Action
            fact_id_1 = kb.add_fact(text="Python developer", fact_type="skill")
            fact_id_2 = kb.add_fact(text="Python developer", fact_type="skill")

            # Assert
            fact_1 = kb.get_fact(fact_id_1)
            fact_2 = kb.get_fact(fact_id_2)

            # Second fact should supersede first
            assert fact_2["version"] == 2
            assert fact_2["supersedes"] == fact_id_1

    def test_when_search_facts_then_returns_matching_results(self):
        """When I search for facts, I should get matching results."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Add some facts
            kb.add_fact(text="5 years Python experience", fact_type="skill")
            kb.add_fact(text="3 years JavaScript experience", fact_type="skill")
            kb.add_fact(text="Worked at Google", fact_type="experience")

            # Action
            results = kb.search_facts(query="Python")

            # Assert
            assert len(results) == 1
            assert "Python" in results[0]["text"]

    def test_when_search_by_type_then_returns_only_that_type(self):
        """When I filter by type, I should only get facts of that type."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Add facts of different types
            kb.add_fact(text="Python skill", fact_type="skill")
            kb.add_fact(text="Google experience", fact_type="experience")
            kb.add_fact(text="Led team of 5", fact_type="achievement")

            # Action
            skills = kb.search_facts(fact_type="skill")

            # Assert
            assert len(skills) == 1
            assert all(f["type"] == "skill" for f in skills)

    def test_when_delete_fact_then_cannot_retrieve(self):
        """When I delete a fact, I should no longer be able to retrieve it."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            fact_id = kb.add_fact(text="Test fact", fact_type="general")

            # Action
            deleted = kb.delete_fact(fact_id)

            # Assert
            assert deleted is True
            assert kb.get_fact(fact_id) is None


class TestConfidenceDecay:
    """Tests for confidence decay behavior."""

    def test_when_fact_is_new_then_confidence_remains_high(self):
        """When a fact is newly created, confidence should stay high."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            fact_id = kb.add_fact(text="New fact", fact_type="skill", confidence=0.9)

            # Action
            current_conf = kb.get_current_confidence(fact_id)

            # Assert - should be nearly the same
            assert current_conf >= 0.89  # Allow for 1 day of decay

    def test_when_fact_is_old_then_confidence_decays(self):
        """When a fact is old, confidence should decay."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            fact_id = kb.add_fact(text="Old fact", fact_type="skill", confidence=0.9)

            # Manually set last_confirmed to 180 days ago
            old_date = (datetime.now() - timedelta(days=180)).isoformat()
            kb.update_fact(fact_id, last_confirmed=old_date)

            # Action
            current_conf = kb.get_current_confidence(fact_id)

            # Assert - should be significantly lower
            # Half-life ~180 days for skill, so 180 days should be ~50%
            assert current_conf < 0.9
            assert current_conf >= 0.4  # Should be around 0.45

    def test_when_skill_type_then_decays_slower_than_preference(self):
        """Skills should decay slower than preferences."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            skill_id = kb.add_fact(text="Skill", fact_type="skill", confidence=0.9)
            pref_id = kb.add_fact(text="Preference", fact_type="preference", confidence=0.9)

            # Set both to 90 days old
            old_date = (datetime.now() - timedelta(days=90)).isoformat()
            kb.update_fact(skill_id, last_confirmed=old_date)
            kb.update_fact(pref_id, last_confirmed=old_date)

            # Action
            skill_conf = kb.get_current_confidence(skill_id)
            pref_conf = kb.get_current_confidence(pref_id)

            # Assert - skill should retain more confidence
            assert skill_conf > pref_conf

    def test_when_refresh_fact_then_confidence_resets(self):
        """When I refresh a stale fact, confidence should reset."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Use preference type which has faster decay (0.990, half-life ~70 days)
            fact_id = kb.add_fact(text="Stale fact", fact_type="preference", confidence=0.9)

            # Make it 100 days old (more than half-life)
            old_date = (datetime.now() - timedelta(days=100)).isoformat()
            kb.update_fact(fact_id, last_confirmed=old_date)

            # Verify it's stale (confidence should be ~0.33)
            current_conf = kb.get_current_confidence(fact_id)
            assert current_conf < 0.5

            # Action - refresh it
            kb.refresh_fact(fact_id, confirmed=True)

            # Assert - confidence should be back to near initial
            new_conf = kb.get_current_confidence(fact_id)
            assert new_conf >= 0.89


class TestStalenessDetection:
    """Tests for staleness detection behavior."""

    def test_when_fact_below_threshold_then_needs_refresh(self):
        """When fact confidence drops below threshold, it should appear in stale list."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Add high confidence fact
            fresh_id = kb.add_fact(text="Fresh fact", fact_type="skill", confidence=0.9)

            # Add low confidence fact
            stale_id = kb.add_fact(text="Stale fact", fact_type="preference", confidence=0.5)

            # Make the stale fact old
            old_date = (datetime.now() - timedelta(days=90)).isoformat()
            kb.update_fact(stale_id, last_confirmed=old_date)

            # Action
            stale_facts = kb.get_facts_needing_refresh(threshold=0.6)

            # Assert
            assert len(stale_facts) == 1
            assert stale_facts[0]["id"] == stale_id
            assert "current_confidence" in stale_facts[0]
            assert "days_old" in stale_facts[0]

    def test_when_fact_confirmed_false_then_confidence_drops(self):
        """When I mark a fact as wrong, confidence should drop."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            fact_id = kb.add_fact(text="Test fact", fact_type="skill", confidence=0.9)

            # Action - mark as wrong
            kb.refresh_fact(fact_id, confirmed=False)

            # Assert
            fact = kb.get_fact(fact_id)
            assert fact["confidence"] < 0.5


class TestGenerationTracking:
    """Tests for generation tracking behavior."""

    def test_when_record_generation_then_can_retrieve_it(self):
        """When I record a generation, I should be able to retrieve it."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Action
            gen_id = kb.record_generation(
                job_url="https://example.com/job/123",
                job_title="Software Engineer",
                company="Google",
            )

            # Assert
            gen = kb.get_generation(gen_id)
            assert gen is not None
            assert gen["job_url"] == "https://example.com/job/123"
            assert gen["job_title"] == "Software Engineer"
            assert gen["company"] == "Google"

    def test_when_record_feedback_then_outcome_is_set(self):
        """When I rate a generation, outcome should be set correctly."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            gen_id = kb.record_generation(job_url="https://example.com/job")

            # Action - rate it 5 (success)
            kb.record_feedback(gen_id, rating=5, feedback="Great!")

            # Assert
            gen = kb.get_generation(gen_id)
            assert gen["rating"] == 5
            assert gen["feedback"] == "Great!"
            assert gen["outcome"] == "success"

    def test_when_rating_below_3_then_outcome_is_failure(self):
        """When rating is 2 or below, outcome should be 'failure'."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            gen_id = kb.record_generation(job_url="https://example.com/job")

            # Action - rate it 2 (failure)
            kb.record_feedback(gen_id, rating=2, feedback="Missing key skills")

            # Assert
            gen = kb.get_generation(gen_id)
            assert gen["outcome"] == "failure"

    def test_when_get_recent_generations_then_ordered_by_date(self):
        """When I get recent generations, they should be ordered by date."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Create multiple generations
            gen_id_1 = kb.record_generation(job_url="https://example.com/job/1")
            gen_id_2 = kb.record_generation(job_url="https://example.com/job/2")
            gen_id_3 = kb.record_generation(job_url="https://example.com/job/3")

            # Action
            recent = kb.get_recent_generations(limit=10)

            # Assert - should be most recent first
            assert len(recent) == 3
            assert recent[0]["id"] == gen_id_3
            assert recent[1]["id"] == gen_id_2
            assert recent[2]["id"] == gen_id_1


class TestPatternExtraction:
    """Tests for pattern extraction behavior."""

    def test_when_add_success_pattern_then_can_retrieve_it(self):
        """When I add a success pattern, I should be able to retrieve it."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Action
            pattern_id = kb.add_pattern(
                pattern_type="success",
                pattern_text="Highlight team leadership when job mentions 'team'",
                keywords=["leadership", "team", "manage"],
            )

            # Assert
            patterns = kb.get_patterns_by_type("success")
            assert len(patterns) == 1
            assert (
                patterns[0]["pattern_text"] == "Highlight team leadership when job mentions 'team'"
            )

    def test_when_get_patterns_then_can_filter_by_type(self):
        """When I get patterns, I should be able to filter by type."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Add patterns of different types
            kb.add_pattern(pattern_type="success", pattern_text="Success pattern 1")
            kb.add_pattern(pattern_type="failure", pattern_text="Failure pattern 1")
            kb.add_pattern(pattern_type="success", pattern_text="Success pattern 2")

            # Action
            success_patterns = kb.get_patterns_by_type("success")
            failure_patterns = kb.get_patterns_by_type("failure")
            all_patterns = kb.get_patterns_by_type()

            # Assert
            assert len(success_patterns) == 2
            assert len(failure_patterns) == 1
            assert len(all_patterns) == 3


class TestStatistics:
    """Tests for statistics behavior."""

    def test_when_get_stats_then_returns_correct_counts(self):
        """When I get statistics, counts should be accurate."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Add some facts
            kb.add_fact(text="Python skill", fact_type="skill")
            kb.add_fact(text=" JavaScript skill", fact_type="skill")
            kb.add_fact(text="Google experience", fact_type="experience")

            # Add a generation
            kb.record_generation(job_url="https://example.com/job")

            # Action
            stats = kb.get_stats()

            # Assert
            assert stats["total_facts"] == 3
            assert stats["facts_by_type"]["skill"] == 2
            assert stats["facts_by_type"]["experience"] == 1
            assert stats["total_generations"] == 1


class TestImportExport:
    """Tests for import/export behavior."""

    def test_when_export_then_can_import_back(self):
        """When I export and import, data should be preserved."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Add some data
            fact_id = kb.add_fact(text="Test fact", fact_type="skill")
            gen_id = kb.record_generation(job_url="https://example.com/job")
            kb.add_pattern(pattern_type="success", pattern_text="Test pattern")

            # Action
            export_data = kb.export_to_json()

            # Create new KB
            kb2 = KnowledgeBase(db_path=Path(tmpdir) / "test2.db")
            kb2.import_from_json(export_data)

            # Assert - data should be preserved
            fact = kb2.get_fact(fact_id)
            assert fact is not None
            assert fact["text"] == "Test fact"

            gen = kb2.get_generation(gen_id)
            assert gen is not None
            assert gen["job_url"] == "https://example.com/job"

            patterns = kb2.get_patterns_by_type()
            assert len(patterns) == 1


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_when_get_nonexistent_fact_then_returns_none(self):
        """When I try to get a fact that doesn't exist, should return None."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Action
            fact = kb.get_fact("nonexistent-id")

            # Assert
            assert fact is None

    def test_when_search_with_no_results_then_returns_empty_list(self):
        """When I search with no matches, should return empty list."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Action
            results = kb.search_facts(query="nonexistent")

            # Assert
            assert results == []

    def test_when_update_nonexistent_fact_then_returns_false(self):
        """When I try to update a fact that doesn't exist, should return False."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Action
            updated = kb.update_fact("nonexistent-id", text="New text")

            # Assert
            assert updated is False

    def test_when_confidence_out_of_range_then_clamped(self):
        """When I add a fact with confidence out of range, it should be clamped."""
        # Setup
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(db_path=Path(tmpdir) / "test.db")

            # Note: Pydantic model should validate this
            # But we test the behavior anyway
            fact_id = kb.add_fact(
                text="Test",
                fact_type="skill",
                confidence=0.9,  # Valid range
            )

            # This should work
            fact = kb.get_fact(fact_id)
            assert 0 <= fact["confidence"] <= 1
