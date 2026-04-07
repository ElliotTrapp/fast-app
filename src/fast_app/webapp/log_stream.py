"""Log streaming for WebSocket broadcast."""

import asyncio
import logging
from collections.abc import Callable


class WebSocketLogHandler(logging.Handler):
    """Logging handler that broadcasts to WebSocket clients."""

    def __init__(self, broadcast_callback: Callable):
        super().__init__()
        self.broadcast_callback = broadcast_callback

    def emit(self, record: logging.LogRecord):
        """Emit a log record to WebSocket clients."""
        try:
            message = self.format(record)

            # Map log levels to emojis
            level_emoji_map = {
                "DEBUG": "🔍",
                "INFO": "ℹ️",
                "WARNING": "⚠️",
                "ERROR": "❌",
                "CRITICAL": "❌",
            }

            level = record.levelname.upper()
            emoji = level_emoji_map.get(level, "•")

            # Broadcast asynchronously
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(
                    self.broadcast_callback(
                        {
                            "type": "log",
                            "level": level.lower(),
                            "emoji": emoji,
                            "message": message,
                        }
                    )
                )
        except Exception:
            # Don't break logging on errors
            pass


class LogBroadcaster:
    """Manages log broadcasting to WebSocket clients."""

    def __init__(self):
        self.clients: list = []
        self.handler: WebSocketLogHandler | None = None

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected WebSocket clients."""
        disconnected = []
        for client in self.clients:
            try:
                await client.send_json(message)
            except Exception:
                disconnected.append(client)

        # Remove disconnected clients
        for client in disconnected:
            self.clients.remove(client)

    def add_client(self, websocket) -> None:
        """Add a WebSocket client."""
        self.clients.append(websocket)

    def remove_client(self, websocket) -> None:
        """Remove a WebSocket client."""
        if websocket in self.clients:
            self.clients.remove(websocket)

    def setup_logging(self) -> None:
        """Replace Click.echo with broadcasting for logger methods."""
        from ..log import logger

        # Create custom handler
        self.handler = WebSocketLogHandler(self.broadcast)
        self.handler.setFormatter(logging.Formatter("%(message)s"))

        # Add to Python logging
        root_logger = logging.getLogger()
        root_logger.addHandler(self.handler)
        root_logger.setLevel(logging.INFO)

        # Monkey-patch logger methods to broadcast
        original_success = logger.success
        original_error = logger.error
        original_warning = logger.warning
        original_info = logger.info

        def patched_success(msg: str):
            original_success(msg)
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(
                    self.broadcast(
                        {"type": "log", "level": "success", "emoji": "✅", "message": msg}
                    )
                )

        def patched_error(msg: str):
            original_error(msg)
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(
                    self.broadcast({"type": "log", "level": "error", "emoji": "❌", "message": msg})
                )

        def patched_warning(msg: str):
            original_warning(msg)
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(
                    self.broadcast(
                        {"type": "log", "level": "warning", "emoji": "⚠️", "message": msg}
                    )
                )

        def patched_info(msg: str):
            original_info(msg)
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(
                    self.broadcast({"type": "log", "level": "info", "emoji": "ℹ️", "message": msg})
                )

        logger.success = patched_success
        logger.error = patched_error
        logger.warning = patched_warning
        logger.info = patched_info

    async def broadcast_state_change(self, old_state: str, new_state: str) -> None:
        """Broadcast a state change event."""
        await self.broadcast(
            {"type": "state_change", "old_state": old_state, "new_state": new_state}
        )

    async def broadcast_progress(self, step: str, progress: float) -> None:
        """Broadcast a progress update."""
        await self.broadcast({"type": "progress", "step": step, "value": progress})


# Global broadcaster instance
log_broadcaster = LogBroadcaster()
