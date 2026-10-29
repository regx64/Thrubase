from .router import Router
from .handlers import health, users


class Server:
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config
        self.router = Router()

    def start(self) -> None:
        self.bind(int(self.config["port"]))
        self.register()
        self.loop()

    def bind(self, port: int) -> None:
        self.port = port

    def register(self) -> None:
        self.router.add("/health", health)
        self.router.add("/users", users)

    def loop(self) -> None:
        request = self.accept()
        self.router.dispatch(request)

    def accept(self) -> str:
        return "/health"

    def wait(self) -> int:
        return 0
