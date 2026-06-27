"""续写取消令牌管理."""
import asyncio
from collections import defaultdict


class CancelManager:
    def __init__(self):
        self._events: dict[str, asyncio.Event] = {}

    def create(self, session_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._events[session_id] = event
        return event

    def cancel(self, session_id: str) -> bool:
        event = self._events.get(session_id)
        if event and not event.is_set():
            event.set()
            return True
        return False

    def remove(self, session_id: str):
        self._events.pop(session_id, None)


cancel_manager = CancelManager()
