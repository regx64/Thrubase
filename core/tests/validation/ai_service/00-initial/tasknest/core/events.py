from collections import defaultdict
from collections.abc import Callable
from typing import Any

Handler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, name: str, handler: Handler) -> None:
        self._handlers[name].append(handler)

    def publish(self, name: str, payload: dict[str, Any]) -> int:
        handlers = self._handlers.get(name, [])
        for handler in handlers:
            handler(payload)
        return len(handlers)
