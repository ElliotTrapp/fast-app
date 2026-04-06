"""Centralized logging with colored debug output."""

import json
from typing import Any, Optional
import click


class Logger:
    """Centralized logger with semantic methods and colored output."""

    def __init__(self):
        self._debug = False

    @property
    def debug(self) -> bool:
        """Check if debug mode is enabled."""
        return self._debug

    @debug.setter
    def debug(self, value: bool) -> None:
        """Set debug mode."""
        self._debug = value

    def _print(self, message: str) -> None:
        """Print message if debug mode is enabled."""
        if self._debug:
            click.echo(message)

    # ============================================================================
    # Header Methods
    # ============================================================================

    def header(self, title: str) -> None:
        """Print a section header."""
        self._print("")
        self._print(click.style(f"  ═══ {title} ═══", fg="cyan", bold=True))

    def subheader(self, title: str) -> None:
        """Print a subheader."""
        self._print(click.style(f"  ── {title} ──", fg="cyan"))

    def step(self, step: str) -> None:
        """Print a processing step."""
        self._print(click.style(f"  ▸ {step}", fg="cyan"))

    # ============================================================================
    # Detail Methods
    # ============================================================================

    def detail(self, label: str, value: Any) -> None:
        """Print a detail with label."""
        if not self._debug:
            return

        if isinstance(value, dict):
            value_str = json.dumps(value, indent=4)
            value_str = "\n".join(f"      {line}" for line in value_str.split("\n"))
        elif isinstance(value, str) and len(value) > 200:
            value_str = f"{value[:200]}... ({len(value)} chars)"
        else:
            value_str = str(value)

        self._print(f"    {click.style(label, fg='blue')}: {value_str}")

    def json(self, label: str, data: dict, max_lines: int = 20) -> None:
        """Print JSON data with formatting."""
        if not self._debug:
            return

        self._print(click.style(f"  📄 {label}", fg="magenta"))
        json_str = json.dumps(data, indent=2)
        lines = json_str.split("\n")[:max_lines]
        for line in lines:
            self._print(f"      {line}")
        if len(json_str.split("\n")) > max_lines:
            self._print(f"      ... ({len(json_str.split(chr(10))) - max_lines} more lines)")

    # ============================================================================
    # API Methods
    # ============================================================================

    def api_request(self, method: str, url: str) -> None:
        """Print API request."""
        self._print(click.style("  → API Request", fg="green", bold=True))
        self._print(f"    {click.style('method', fg='blue')}: {method}")
        self._print(f"    {click.style('url', fg='blue')}: {url}")

    def api_response(self, status_code: int) -> None:
        """Print API response status."""
        color = "green" if status_code < 400 else "red"
        self._print(click.style("  ← API Response", fg="green", bold=True))
        self._print(f"    {click.style('status', fg=color)}: {status_code}")

    # ============================================================================
    # LLM Methods
    # ============================================================================

    def llm_request(self, endpoint: str, model: str, prompt_length: int) -> None:
        """Print LLM request."""
        self._print(click.style("  → LLM Request", fg="green", bold=True))
        self._print(f"    {click.style('endpoint', fg='blue')}: {endpoint}")
        self._print(f"    {click.style('model', fg='blue')}: {model}")
        self._print(f"    {click.style('prompt_length', fg='blue')}: {prompt_length} chars")

    def llm_response(self, response_length: int, preview: Optional[str] = None) -> None:
        """Print LLM response."""
        self._print(click.style("  ← LLM Response", fg="green", bold=True))
        self._print(f"    {click.style('response_length', fg='blue')}: {response_length} chars")
        if preview:
            preview_str = preview[:300] + "..." if len(preview) > 300 else preview
            self._print(f"    {click.style('preview', fg='blue')}:")
            for line in preview_str.split("\n")[:5]:
                self._print(f"      {line}")

    def llm_call(self, call_type: str, input_summary: dict) -> None:
        """Print LLM call initialization."""
        self._print(click.style(f"  🤖 LLM Call: {call_type}", fg="yellow", bold=True))
        for key, value in input_summary.items():
            if isinstance(value, str) and len(value) > 60:
                value = f"{value[:60]}..."
            self._print(f"    {click.style(key, fg='blue')}: {value}")

    def llm_result(self, result_type: str, result_summary: dict) -> None:
        """Print LLM call result."""
        self._print(click.style(f"  ✓ LLM Result: {result_type}", fg="yellow"))
        for key, value in result_summary.items():
            if isinstance(value, str) and len(value) > 60:
                value = f"{value[:60]}..."
            elif isinstance(value, list):
                value = f"{len(value)} items"
            self._print(f"    {click.style(key, fg='blue')}: {value}")

    # ============================================================================
    # Cache Methods
    # ============================================================================

    def cache_hit(self, cache_type: str, path: str) -> None:
        """Print cache hit."""
        self._print(click.style("  ♻️  Cache hit", fg="green"))
        self._print(f"    {click.style('type', fg='blue')}: {cache_type}")
        self._print(f"    {click.style('path', fg='blue')}: {path}")

    def cache_save(self, cache_type: str, path: str) -> None:
        """Print cache save."""
        self._print(click.style("  💾 Cache save", fg="green"))
        self._print(f"    {click.style('type', fg='blue')}: {cache_type}")
        self._print(f"    {click.style('path', fg='blue')}: {path}")

    def cache_search(self, search_type: str, target: str) -> None:
        """Print cache search."""
        self._print(click.style("  🔍 Cache search", fg="cyan"))
        self._print(f"    {click.style('type', fg='blue')}: {search_type}")
        self._print(f"    {click.style('target', fg='blue')}: {target}")

    def cache_found(self, path: str) -> None:
        """Print cache found."""
        self._print(click.style("  ✓ Cache found", fg="green"))
        self._print(f"    {click.style('path', fg='blue')}: {path}")

    # ============================================================================
    # Status Methods (always print, regardless of debug mode)
    # ============================================================================

    def error(self, message: str) -> None:
        """Print error message in red."""
        click.echo(click.style(f"  ❌ {message}", fg="red", bold=True))

    def warning(self, message: str) -> None:
        """Print warning message in yellow."""
        click.echo(click.style(f"  ⚠️  {message}", fg="yellow"))

    def success(self, message: str) -> None:
        """Print success message in green."""
        click.echo(click.style(f"  ✅ {message}", fg="green"))

    def info(self, message: str) -> None:
        """Print info message."""
        click.echo(f"  ℹ️  {message}")

    def verbose(self, message: str, is_verbose: bool = False) -> None:
        """Print verbose message (only if verbose mode is on)."""
        if is_verbose:
            click.echo(f"  {message}")


# Global singleton logger
logger = Logger()
