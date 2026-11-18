from collections.abc import Sequence
from decimal import Decimal
from typing import Literal


def moving_averages(closes: Sequence[Decimal]) -> tuple[Decimal, Decimal]:
    return sum(closes[-20:]) / 20, sum(closes[-50:]) / 50


def crossover(closes: Sequence[Decimal]) -> Literal["up", "down"] | None:
    if len(closes) < 51:
        return None

    def spread(window: Sequence[Decimal]) -> Decimal:
        fast, slow = moving_averages(window)
        return fast - slow

    previous = spread(closes[-51:-1])
    current = spread(closes[-50:])
    if previous <= 0 < current:
        return "up"
    if previous >= 0 > current:
        return "down"
    return None
