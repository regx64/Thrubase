def orchestrate() -> None:
    step_one()
    step_two()
    step_three()


def small() -> None:
    step_one()


def step_one() -> None:
    pass


def step_two() -> None:
    pass


def step_three() -> None:
    pass


def _private_driver() -> None:
    step_one()
    step_two()
    step_three()
    step_one()
