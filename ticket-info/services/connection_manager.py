from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._active.add(ws)

    def disconnect(self, ws: WebSocket):
        self._active.discard(ws)

    async def broadcast(self, data: dict):
        dead = set()
        for ws in self._active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._active -= dead
