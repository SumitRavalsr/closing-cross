from collections.abc import Sequence
from decimal import Decimal
from typing import Literal


def crossover(closes: Sequence[Decimal]) -> Literal["up", "down"] | None:
    if len(closes) < 51:
        return None

    def spread(window: Sequence[Decimal]) -> Decimal:
        return sum(window[-20:]) / 20 - sum(window[-50:]) / 50

    previous = spread(closes[-51:-1])
    current = spread(closes[-50:])
    if previous <= 0 < current:
        return "up"
    if previous >= 0 > current:
        return "down"
    return None
