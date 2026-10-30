from .base import Gateway
from ..util.money import Money


class Middle(Gateway):
    pass


class CardGateway(Middle):
    def charge(self, amount: Money) -> bool:
        ok = self.validate(amount)
        return ok and super().charge(amount)
