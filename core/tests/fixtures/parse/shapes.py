import functools


def deco(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


@deco
@functools.lru_cache(maxsize=None)
def decorated(x: int) -> int:
    return x + 1


async def fetch(url: str) -> str:
    async with session() as s:
        return await s.get(url)


def outer() -> int:
    def middle() -> int:
        def inner() -> int:
            return 3

        return inner()

    return middle()


class Outer:
    class Inner:
        def method(self) -> int:
            return 1

    async def amethod(self) -> None:
        pass

    @property
    def value(self) -> int:
        return 1

    @value.setter
    def value(self, v: int) -> None:
        pass


def session():
    raise NotImplementedError
