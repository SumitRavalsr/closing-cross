from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

from closing_cross.domain.candles import DataError

PAISE = Decimal('0.01')
ZERO = Decimal('0.00')


def money(value: Decimal, rounding: str = ROUND_HALF_UP) -> Decimal:
    return value.quantize(PAISE, rounding=rounding)


@dataclass(frozen=True)
class PaperTerms:
    opening_cash: Decimal = Decimal('1000.00')
    allocation: Decimal = Decimal('1000.00')
    fee: Decimal = Decimal('2.00')
    slippage_per_share: Decimal = Decimal('1.00')

    @classmethod
    def parse(cls, values: list[str]) -> 'PaperTerms':
        try:
            amounts = [Decimal(value) for value in values]
            if any(not amount.is_finite() or amount < ZERO or amount != money(amount) for amount in amounts):
                raise InvalidOperation
        except InvalidOperation:
            raise DataError('Paper ledger settings must be nonnegative rupee amounts with at most two decimal places') from None
        if min(amounts[:2]) == ZERO:
            raise DataError('Paper opening cash and allocation must be positive')
        return cls(*(money(amount) for amount in amounts))


@dataclass(frozen=True)
class PaperSession:
    session: str
    open: Decimal
    close: Decimal
    cross: Literal['up', 'down'] | None


@dataclass
class PaperPosition:
    cash: Decimal
    shares: int = 0
    entry_cost: Decimal = ZERO
    realized: Decimal = ZERO

    def settle_open(self, day: PaperSession, signal: dict, terms: PaperTerms) -> dict | None:
        buy = signal['side'] == 'buy'
        price = (money(day.open + terms.slippage_per_share, ROUND_CEILING) if buy
                 else money(day.open - terms.slippage_per_share, ROUND_FLOOR))
        signal['fill_session'] = day.session
        if price <= ZERO:
            signal.update(status='skipped', reason='nonpositive_fill_price')
            return None
        budget = min(self.cash, terms.allocation)
        quantity = int(max(ZERO, budget - terms.fee) // price) if buy else self.shares
        gross = price * quantity
        cash_change = -gross - terms.fee if buy else gross - terms.fee
        if quantity == 0:
            signal.update(status='skipped', reason='insufficient_cash' if self.cash < price + terms.fee else 'zero_shares')
            return None
        if self.cash + cash_change < ZERO:
            signal.update(status='skipped', reason='insufficient_cash_for_exit_fee')
            return None

        self.cash += cash_change
        trade_pnl = None
        if buy:
            self.shares = quantity
            self.entry_cost = -cash_change
        else:
            self.shares = 0
            trade_pnl = cash_change - self.entry_cost
            self.realized += trade_pnl
            self.entry_cost = ZERO
        signal['status'] = 'filled'
        return {
            'signal_session': signal['session'], 'fill_session': day.session,
            'side': signal['side'], 'quantity': quantity,
            'raw_open': str(day.open), 'price': str(price),
            'fee': str(terms.fee), 'slippage_per_share': str(abs(price - day.open)),
            'cash_change': str(cash_change), 'cash_after': str(self.cash),
            'realized_pnl': str(trade_pnl) if trade_pnl is not None else None,
        }

    def mark_close(self, day: PaperSession, terms: PaperTerms) -> dict:
        equity = money(self.cash + self.shares * day.close)
        return {
            'session': day.session, 'close': str(day.close), 'shares': self.shares,
            'cash': str(self.cash), 'equity': str(equity), 'net_pnl': str(equity - terms.opening_cash),
        }

    def signal_at_close(self, day: PaperSession) -> dict | None:
        if day.cross is None:
            return None
        buy = day.cross == 'up'
        signal = {'session': day.session, 'side': 'buy' if buy else 'sell', 'status': 'pending'}
        if buy and self.shares:
            signal.update(status='skipped', reason='already_long')
        elif not buy and not self.shares:
            signal.update(status='skipped', reason='flat_position')
        return signal


def build_ledger(sessions: list[PaperSession], terms: PaperTerms) -> dict:
    if not sessions:
        raise DataError('The paper ledger requires at least one session')
    position = PaperPosition(terms.opening_cash)
    pending = None
    fills = []
    signals = []
    daily = []

    for day in sessions:
        if pending is not None:
            fill = position.settle_open(day, pending, terms)
            if fill:
                fills.append(fill)
            pending = None

        daily.append(position.mark_close(day, terms))
        signal = position.signal_at_close(day)
        if signal:
            if signal['status'] == 'pending':
                pending = signal
            signals.append(signal)

    return {
        'ledger_version': 'one-stock-price-return-v1',
        'terms': {name: str(value) for name, value in vars(terms).items()},
        'summary': {**daily[-1], 'realized_pnl': str(position.realized)},
        'signals': signals, 'fills': fills, 'daily': daily,
    }
