"""Spinner context manager for CLI progress indication.

Wraps the progress.Spinner in a context manager with a background
animation thread, eliminating the boilerplate spinner setup/teardown
pattern that was duplicated across ollama.py and job_extractor.py.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from progress.spinner import Spinner


class SpinnerContextManager:
    """Context manager that animates a spinner in a background thread.

    Usage::

        with SpinnerContextManager("🤖 Generating questions ") as sp:
            result = some_long_operation()
        # Spinner automatically stops and finishes when the block exits

    Args:
        message: The spinner message prefix (e.g., "🤖 Generating questions ").
        interval: Seconds between spinner animation ticks (default 0.1).
    """

    def __init__(self, message: str, interval: float = 0.1):
        self._spinner = Spinner(message)
        self._interval = interval
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    def _spin(self) -> None:
        """Background thread target that animates the spinner."""
        while not self._done.is_set():
            self._spinner.next()
            time.sleep(self._interval)

    def __enter__(self) -> SpinnerContextManager:
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._done.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        self._spinner.finish()
