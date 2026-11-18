from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


class DataError(ValueError):
    """A data or configuration problem safe to report to the operator."""


@dataclass(frozen=True)
class Candle:
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @classmethod
    def parse(cls, session: date, values: list[object], source: str) -> 'Candle':
        try:
            candle = cls(session, *(Decimal(str(value)) for value in values))
        except (InvalidOperation, TypeError):
            raise DataError(f'{source} contains malformed OHLCV for {session}') from None
        if (
            not all(getattr(candle, field).is_finite() for field in FIELDS)
            or not 0 < candle.low <= min(candle.open, candle.close)
            or candle.high < max(candle.open, candle.close)
            or candle.volume < 0
            or candle.volume != candle.volume.to_integral_value()
        ):
            raise DataError(f'{source} contains invalid OHLCV for {session}')
        return candle


FIELDS = ('open', 'high', 'low', 'close', 'volume')
