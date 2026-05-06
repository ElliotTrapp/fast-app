"""WebSocket connection manager and endpoint for Fast-App webapp."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .log_stream import log_broadcaster


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log_broadcaster.add_client(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        log_broadcaster.remove_client(websocket)

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Echo back for keepalive
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


def setup_websocket(app: FastAPI):
    """Register WebSocket endpoint on the FastAPI app."""
    app.websocket("/ws")(websocket_endpoint)
