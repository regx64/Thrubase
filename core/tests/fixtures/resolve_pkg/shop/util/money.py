class Money:
    def __init__(self, cents: int) -> None:
        self.cents = cents

    def positive(self) -> bool:
        return self.cents > 0


def parse(text: str) -> Money:
    return Money(int(text))


def add(a: Money, b: Money) -> Money:
    return Money(a.cents + b.cents)


def format_price(m: Money) -> str:
    return str(m.cents)
