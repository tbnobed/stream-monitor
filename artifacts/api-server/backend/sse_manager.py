import asyncio
import json
from typing import AsyncIterator
from datetime import datetime


class SSEManager:
    def __init__(self):
        self._queues: list[asyncio.Queue] = []

    def add_listener(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.append(q)
        return q

    def remove_listener(self, q: asyncio.Queue):
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    async def broadcast(self, event_type: str, data: dict):
        payload = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })
        dead = []
        for q in list(self._queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.remove_listener(q)

    async def listen(self, q: asyncio.Queue) -> AsyncIterator[str]:
        try:
            while True:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
                yield msg
        except asyncio.TimeoutError:
            yield json.dumps({"type": "ping"})


sse_manager = SSEManager()
