"""CLI package for fast-app — re-exports `main` click group and utility functions."""

from ..utils import sanitize_name
from .auth import register_commands as _register_auth
from .connection import register_commands as _register_connection
from .interactive import ask_questions_interactive
from .knowledge import register_commands as _register_knowledge
from .list_cmd import register_commands as _register_list
from .main import main
from .profile import register_commands as _register_profile
from .status import register_commands as _register_status

_register_auth(main)
_register_connection(main)
_register_knowledge(main)
_register_list(main)
_register_profile(main)
_register_status(main)

__all__ = ["main", "ask_questions_interactive", "sanitize_name"]
