"""Per-user state management for webapp job processing.

Provides PerUserStateManager which manages isolated StateManager instances
per user, enabling multi-user support. In auth-disabled mode, all requests
use user_id=1 for backward compatibility.
"""

import threading
from pathlib import Path

from .state import StateManager


class PerUserStateManager:
    """Manages per-user StateManager instances with thread-safe access.

    Each user gets their own StateManager with a separate state file
    at ~/.fast-app/state_{user_id}.json. This ensures complete isolation
    between users' job processing state.
    """

    def __init__(self, state_dir: Path | None = None):
        self._state_dir = state_dir or Path.home() / ".fast-app"
        self._states: dict[int, StateManager] = {}
        self._lock = threading.Lock()

    def get_state(self, user_id: int) -> StateManager:
        """Get or create a StateManager for the given user.

        Args:
            user_id: The user's database ID. In auth-disabled mode, this is 1.

        Returns:
            StateManager instance for the user.
        """
        with self._lock:
            if user_id not in self._states:
                state_file = self._state_dir / f"state_{user_id}.json"
                self._states[user_id] = StateManager(
                    state_dir=self._state_dir,
                    state_file=state_file,
                )
            return self._states[user_id]

    def remove_state(self, user_id: int) -> None:
        """Remove the StateManager for a user and delete its state file.

        Args:
            user_id: The user's database ID.
        """
        with self._lock:
            if user_id in self._states:
                self._states.pop(user_id)
                state_file = self._state_dir / f"state_{user_id}.json"
                if state_file.exists():
                    state_file.unlink()

    def is_active(self, user_id: int) -> bool:
        """Check if a user has an active job.

        Args:
            user_id: The user's database ID.

        Returns:
            True if the user has an active (processing or waiting) job.
        """
        return self.get_state(user_id).is_active()


per_user_state = PerUserStateManager()
