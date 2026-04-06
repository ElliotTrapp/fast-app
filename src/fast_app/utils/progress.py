"""Progress indicator utilities."""

import time
from collections.abc import Iterator
from contextlib import contextmanager

import click


class ProgressIndicator:
    """Simple text-based progress indicator for long operations."""

    def __init__(self, message: str, show_spinner: bool = True):
        self.message = message
        self.show_spinner = show_spinner
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_index = 0
        self._running = False

    def _update_spinner(self) -> str:
        if not self.show_spinner:
            return ""
        char = self.spinner_chars[self.spinner_index % len(self.spinner_chars)]
        self.spinner_index += 1
        return char

    def start(self) -> None:
        """Start the progress indicator."""
        self._running = True
        self._write_progress()

    def _write_progress(self) -> None:
        spinner = self._update_spinner()
        if self.show_spinner:
            click.echo(f"\r{spinner} {self.message}...", nl=False)
        else:
            click.echo(f"{self.message}...", nl=False)

    def update(self, message: str | None = None) -> None:
        """Update the progress message."""
        if message:
            self.message = message
        if self._running:
            self._write_progress()

    def complete(self, final_message: str | None = None) -> None:
        """Mark as complete."""
        self._running = False
        msg = final_message or f"✓ {self.message}"
        click.echo(f"\r✓ {msg.ljust(60)}")

    def fail(self, error_message: str) -> None:
        """Mark as failed."""
        self._running = False
        click.echo(f"\r✗ {error_message.ljust(60)}")


@contextmanager
def progress_bar(total: int, label: str = "Processing", show_eta: bool = True) -> Iterator[list]:
    """Context manager for a progress bar.

    Usage:
        with progress_bar(3, "Processing files") as progress:
            progress[0] += 1  # After step 1
            progress[0] += 1  # After step 2
            progress[0] += 1  # After step 3
    """
    progress = [0]
    start_time = time.time()

    try:
        with click.progressbar(
            length=total,
            label=label,
            show_eta=show_eta,
            show_percent=True,
            width=40,
        ) as bar:
            bar.update(0)
            yield progress
            bar.update(total)
    finally:
        pass


def show_spinner(message: str, duration: float = 0.1):
    """Show a spinner animation while waiting.

    Args:
        message: Message to display
        duration: Duration per spinner frame in seconds
    """
    import itertools
    import threading

    spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])

    def spin():
        while not done:
            char = next(spinner)
            click.echo(f"\r{char} {message}", nl=False)
            time.sleep(duration)

    done = False
    thread = threading.Thread(target=spin)
    thread.start()

    return lambda: (
        setattr(__builtins__, "done", True),
        thread.join(),
        click.echo(f"\r✓ {message}" + " " * 10),
    )
