"""Auth CLI command group (signup, login, whoami, logout) and token helpers."""

import json
from pathlib import Path

import click

from ..log import logger


def _token_path() -> Path:
    """Get the path to the auth token file."""
    xdg_data = __import__("os").environ.get("XDG_DATA_HOME", "~/.local/share")
    token_dir = Path(xdg_data).expanduser() / "fast-app"
    token_dir.mkdir(parents=True, exist_ok=True)
    return token_dir / "auth.json"


def _save_token(token: str) -> None:
    """Save the auth token to disk."""
    token_path = _token_path()
    token_path.write_text(json.dumps({"access_token": token}))
    token_path.chmod(0o600)


def _load_token() -> str | None:
    """Load the auth token from disk. Returns None if not found."""
    token_path = _token_path()
    if not token_path.exists():
        return None
    try:
        data = json.loads(token_path.read_text())
        return data.get("access_token")
    except (json.JSONDecodeError, KeyError):
        return None


def _remove_token() -> None:
    """Remove the auth token from disk."""
    token_path = _token_path()
    if token_path.exists():
        token_path.unlink()


def _get_user_id(config_path: str | None) -> int:
    """Get the current user ID from the stored auth token.

    Falls back to user_id=1 when auth is disabled (no token or no JWT secret).
    """
    token = _load_token()
    if token:
        try:
            from ..services.auth_core import JWT_SECRET, decode_access_token

            if JWT_SECRET:
                payload = decode_access_token(token)
                return int(payload.get("sub", 1))
        except Exception:
            pass
    return 1


def register_commands(main: click.Group) -> None:
    """Register auth commands on the main group."""
    main.add_command(auth)


@click.group()
def auth():
    """Authentication commands (signup, login, logout, whoami)."""
    pass


@auth.command()
@click.option("--email", "-e", required=True, help="Email address")
@click.option("--password", "-p", required=True, help="Password", hide_input=True)
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def signup(email: str, password: str, config_path: str | None) -> None:
    """Create a new user account.

    Creates a user with the given email and password, then
    stores the authentication token for CLI use.
    """
    try:
        from ..db import get_session, init_db
        from ..models.db_models import User
        from ..services.auth import create_access_token, hash_password

        init_db()
        session = next(get_session())

        existing = session.exec(
            __import__("sqlmodel").select(User).where(User.email == email)
        ).first()
        if existing:
            raise click.ClickException(f"Email '{email}' is already registered")

        user = User(email=email, hashed_password=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)

        token = create_access_token(user.id)

        _save_token(token)
        click.echo(click.style(f"✓ Account created for {email}", fg="green"))
        click.echo(click.style("  Token saved. You are now logged in.", fg="green"))
    except ValueError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise click.ClickException(f"Signup failed: {e}")


@auth.command()
@click.option("--email", "-e", required=True, help="Email address")
@click.option("--password", "-p", required=True, help="Password", hide_input=True)
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def login(email: str, password: str, config_path: str | None) -> None:
    """Log in with email and password.

    Authenticates and stores the token for subsequent CLI commands.
    """
    try:
        from sqlmodel import select

        from ..db import get_session, init_db
        from ..models.db_models import User
        from ..services.auth import create_access_token, hash_password, verify_password

        init_db()
        session = next(get_session())

        user = session.exec(select(User).where(User.email == email)).first()

        if user is None:
            hash_password(password)  # Prevent timing attack
            raise click.ClickException("Invalid email or password")

        if not verify_password(password, user.hashed_password):
            raise click.ClickException("Invalid email or password")

        if not user.is_active:
            raise click.ClickException("Account is deactivated")

        token = create_access_token(user.id)

        _save_token(token)
        click.echo(click.style(f"✓ Logged in as {email}", fg="green"))
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise click.ClickException(f"Login failed: {e}")


@auth.command()
def whoami() -> None:
    """Show the currently authenticated user."""
    try:
        from ..db import get_session
        from ..models.db_models import User
        from ..services.auth import decode_access_token

        token = _load_token()
        if not token:
            raise click.ClickException("Not logged in. Run 'fast-app auth login' first.")

        payload = decode_access_token(token)
        user_id = int(payload.get("sub", 0))

        session = next(get_session())
        user = session.get(User, user_id)

        if user is None:
            raise click.ClickException("User not found. Token may be invalid.")

        click.echo(f"Email:     {user.email}")
        click.echo(f"User ID:   {user.id}")
        click.echo(f"Active:    {user.is_active}")
        click.echo(f"Created:   {user.created_at}")
    except ValueError as e:
        raise click.ClickException(f"Authentication error: {e}")
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Whoami error: {e}")
        raise click.ClickException(f"Whoami failed: {e}")


@auth.command()
def logout() -> None:
    """Log out by removing the stored token."""
    _remove_token()
    click.echo(click.style("✓ Logged out", fg="green"))
