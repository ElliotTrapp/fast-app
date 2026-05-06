"""Tests for per-user state management.

Tests PerUserStateManager isolation, resolve_user_id, and state file paths.

Required deps: pip install -e ".[auth]"
"""

import pytest


def _check_deps():
    """Check if auth dependencies are installed, skip if not."""
    try:
        import sqlmodel  # noqa: F401
    except ImportError:
        pytest.skip("auth deps not installed - pip install -e '.[auth]'")


@pytest.fixture(autouse=True)
def check_auth_deps():
    """Skip all tests in this module if auth deps aren't installed."""
    _check_deps()
    yield


from fast_app.webapp.per_user_state import PerUserStateManager  # noqa: E402
from fast_app.webapp.state import JobState, StateManager  # noqa: E402


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for state files."""
    return tmp_path


class TestPerUserStateManager:
    def test_get_state_creates_new_state_for_new_user(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        state = manager.get_state(1)
        assert state is not None
        assert state.state == JobState.IDLE

    def test_get_state_returns_same_instance_for_same_user(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        state1 = manager.get_state(1)
        state2 = manager.get_state(1)
        assert state1 is state2

    def test_get_state_returns_different_instances_for_different_users(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        state1 = manager.get_state(1)
        state2 = manager.get_state(2)
        assert state1 is not state2

    def test_per_user_state_isolation(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        state1 = manager.get_state(1)
        state2 = manager.get_state(2)

        state1.start_job("job-1", "https://example.com", {"force": False})
        assert state1.is_active()
        assert not state2.is_active()

        state2.start_job("job-2", "https://other.com", {"force": True})
        assert state2.is_active()
        assert state1.job_id == "job-1"
        assert state2.job_id == "job-2"

    def test_remove_state_cleans_up(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        state = manager.get_state(1)
        state.start_job("job-1", "https://example.com", {"force": False})

        manager.remove_state(1)

        state_new = manager.get_state(1)
        assert state_new.state == JobState.IDLE
        assert state_new.job_id is None

    def test_remove_nonexistent_user_is_noop(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        manager.remove_state(999)

    def test_is_active_returns_false_for_new_user(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        assert not manager.is_active(1)

    def test_is_active_returns_true_for_active_job(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        state = manager.get_state(1)
        state.start_job("job-1", "https://example.com", {"force": False})
        assert manager.is_active(1)

    def test_state_file_per_user(self, temp_dir):
        manager = PerUserStateManager(state_dir=temp_dir)
        state1 = manager.get_state(1)
        state2 = manager.get_state(2)

        assert state1.state_file == temp_dir / "state_1.json"
        assert state2.state_file == temp_dir / "state_2.json"

    def test_state_file_default_is_state_json(self, temp_dir):
        sm = StateManager(state_dir=temp_dir)
        assert sm.state_file == temp_dir / "state.json"


class TestResolveUserId:
    def test_returns_user_id_when_authenticated(self):
        from fast_app.webapp.dependencies import resolve_user_id

        class FakeUser:
            id = 42

        assert resolve_user_id(FakeUser()) == 42

    def test_returns_one_when_none(self):
        from fast_app.webapp.dependencies import resolve_user_id

        assert resolve_user_id(None) == 1


class TestStateManagerWithCustomStateFile:
    def test_state_manager_with_custom_state_file(self, temp_dir):
        custom_file = temp_dir / "state_99.json"
        sm = StateManager(state_dir=temp_dir, state_file=custom_file)
        assert sm.state_file == custom_file

    def test_state_manager_default_state_file(self, temp_dir):
        sm = StateManager(state_dir=temp_dir)
        assert sm.state_file == temp_dir / "state.json"

    def test_state_persistence_with_custom_file(self, temp_dir):
        custom_file = temp_dir / "state_5.json"
        sm = StateManager(state_dir=temp_dir, state_file=custom_file)
        sm.start_job("job-5", "https://example.com", {"force": False})
        assert sm.is_active()

        sm2 = StateManager(state_dir=temp_dir, state_file=custom_file)
        assert sm2.is_active()
        assert sm2.job_id == "job-5"
