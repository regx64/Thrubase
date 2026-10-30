from .errors import ConfigError


def load_config(path: str) -> dict[str, str]:
    raw = read_file(path)
    data = parse_text(raw)
    validate(data)
    return data


def read_file(path: str) -> str:
    with open(path) as fh:
        return fh.read()


def parse_text(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def validate(data: dict[str, str]) -> None:
    if "port" not in data:
        raise ConfigError("port is required")
