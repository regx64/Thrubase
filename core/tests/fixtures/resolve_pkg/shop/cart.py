from __future__ import annotations

from . import util
from .payments.base import Gateway
from .payments.card import CardGateway
from .util import money
from .util.money import Money, add as plus
import shop.util.money as m2


class Base:
    def total(self) -> Money:
        return self.sum_items()

    def sum_items(self) -> Money:
        return Money(0)

    @classmethod
    def create(cls) -> "Base":
        return cls.empty()

    @classmethod
    def empty(cls) -> "Base":
        return cls()


class Cart(Base):
    gateway: Gateway

    def __init__(self) -> None:
        self.items: list[Money] = []
        self.gateway = CardGateway()
        self.helper = Helper()

    def sum_items(self) -> Money:
        base = super().sum_items()
        return plus(base, money.parse("1"))

    def checkout(self, gw: Gateway) -> bool:
        def inner() -> str:
            return util.money.format_price(self.total())

        label = inner()
        m2.add(self.total(), Money(1))
        self.helper.log(label)
        return gw.charge(self.total()) and self.gateway.charge(self.total())


class Helper:
    def log(self, text: str) -> None:
        Helper.write(text)

    @staticmethod
    def write(text: str) -> None:
        return None


def build() -> Cart:
    cart = Cart.create()
    c = Cart()
    c.checkout(CardGateway())
    return cart  # type: ignore[return-value]
