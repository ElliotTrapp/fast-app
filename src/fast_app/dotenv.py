"""Load environment variables from .env file.

Provides a ``load_dotenv()`` function that reads a ``.env`` file from the
project root and sets the variables as OS environment variables.  If
``python-dotenv`` is not installed, the function is a no-op — the app still
works with manually-set env vars.

The ``.env`` file is looked up by walking parent directories from the
package location until a directory containing ``pyproject.toml`` is found.
If that fails, the current working directory is used as a fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_project_root: Path | None = None


def _find_project_root() -> Path:
    """Find the project root directory containing pyproject.toml.

    Walks parent directories from the package location until a directory
    containing ``pyproject.toml`` is found.  Falls back to the current
    working directory.

    Returns:
        The project root directory path.
    """
    global _project_root
    if _project_root is not None:
        return _project_root

    # Walk from this file's location upward
    current = Path(__file__).resolve().parent
    for _ in range(20):  # safety limit
        if (current / "pyproject.toml").exists():
            _project_root = current
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback: current working directory
    _project_root = Path.cwd()
    return _project_root


def load_dotenv() -> None:
    """Load environment variables from a .env file in the project root.

    If ``python-dotenv`` is not installed, this is a no-op.  The app
    continues to work with manually-set environment variables.

    The ``.env`` file must be in the project root (same directory as
    ``pyproject.toml``).  Existing environment variables are NOT
    overwritten — ``.env`` values only fill in unset variables.
    """
    try:
        from dotenv import load_dotenv as _load_dotenv
    except ImportError:
        logger.debug("python-dotenv not installed; .env file not loaded")
        return

    project_root = _find_project_root()
    env_file = project_root / ".env"

    if env_file.exists():
        _load_dotenv(dotenv_path=str(env_file), override=False)
        logger.debug("Loaded environment from %s", env_file)
    else:
        logger.debug("No .env file found at %s", env_file)
