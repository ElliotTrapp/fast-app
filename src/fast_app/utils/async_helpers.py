"""Async helpers for running coroutines in synchronous contexts."""

from __future__ import annotations

import asyncio
import concurrent.futures


def run_async(coro) -> object:
    """Run an async coroutine in a synchronous context.

    Handles three cases:
    1. No event loop exists — create one and run the coroutine.
    2. An event loop exists but is not running — use it directly.
    3. An event loop is already running (e.g., inside FastAPI) —
       offload to a separate thread via ThreadPoolExecutor.

    Args:
        coro: An asyncio coroutine object to execute.

    Returns:
        The return value of the coroutine.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
