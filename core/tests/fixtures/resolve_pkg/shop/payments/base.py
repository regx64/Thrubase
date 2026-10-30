from ..util.money import Money


class Gateway:
    def charge(self, amount: Money) -> bool:
        return self.validate(amount)

    def validate(self, amount: Money) -> bool:
        return amount.positive()
