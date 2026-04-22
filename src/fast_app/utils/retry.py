"""Retry utilities for API calls with exponential backoff."""

import time
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

import requests

T = TypeVar("T")


class RetryableError(Exception):
    pass


class NonRetryableError(Exception):
    pass


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (requests.RequestException,),
    retryable_status_codes: tuple[int, ...] = (429, 502, 503, 504),
) -> Callable:
    """Decorator to retry a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Factor to multiply delay by each retry
        retryable_exceptions: Exceptions that should trigger retry
        retryable_status_codes: HTTP status codes that should trigger retry

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Exception | None = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    return result
                except NonRetryableError:
                    raise
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        import click

                        click.echo(
                            click.style(
                                (
                                    f"  ⚠️  Attempt {attempt + 1}/{max_retries + 1} "
                                    f"failed: {e}. Retrying in {delay:.1f}s..."
                                ),
                                fg="yellow",
                            )
                        )
                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        raise RetryableError(
                            f"Operation failed after {max_retries + 1} attempts: {e}"
                        ) from e

            raise last_exception if last_exception else RetryableError("Operation failed")

        return wrapper

    return decorator


def should_retry(status_code: int, retryable_codes: tuple[int, ...] = (429, 502, 503, 504)) -> bool:
    """Check if an HTTP status code should trigger a retry.

    Args:
        status_code: HTTP status code
        retryable_codes: Codes that should trigger retry

    Returns:
        True if should retry, False otherwise
    """
    return status_code in retryable_codes
