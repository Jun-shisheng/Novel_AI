"""续写取消令牌管理."""
import asyncio


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

    def cancel_all(self) -> int:
        """取消所有活跃的续写会话，返回取消数量。"""
        count = 0
        for session_id in list(self._events.keys()):
            if self.cancel(session_id):
                count += 1
        return count

    def remove(self, session_id: str):
        self._events.pop(session_id, None)


cancel_manager = CancelManager()
