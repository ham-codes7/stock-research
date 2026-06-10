from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}

    async def connect(self, request_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[request_id] = websocket

    def disconnect(self, request_id: str):
        self.active_connections.pop(request_id, None)

    async def send(self, request_id: str, data: dict):
        websocket = self.active_connections.get(request_id)
        if websocket:
            await websocket.send_json(data)

    def send_wrapper(self, request_id: str):
        async def _send(event: dict):
            await self.send(request_id, event)
        return _send

manager = ConnectionManager()