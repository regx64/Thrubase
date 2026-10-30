from .errors import RouteError


class Router:
    def __init__(self) -> None:
        self.routes = {}

    def add(self, path, handler) -> None:
        self.routes[path] = handler

    def dispatch(self, path: str) -> str:
        handler = self.find(path)
        response = handler()
        return self.render(response)

    def find(self, path: str):
        if path not in self.routes:
            raise RouteError(path)
        return self.routes[path]

    def render(self, body: str) -> str:
        return encode(body)


def encode(body: str) -> str:
    return body.upper()
