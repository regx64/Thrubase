from .config import load_config
from .server import Server


def main() -> int:
    config = load_config("app.toml")
    server = Server(config)
    server.start()
    return server.wait()
