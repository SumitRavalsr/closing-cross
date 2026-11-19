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


def build_ledger(sessions: list[PaperSession], terms: PaperTerms) -> dict:
    if not sessions:
        raise DataError('The paper ledger requires at least one session')
    cash = terms.opening_cash
    shares = 0
    entry_cost = ZERO
    realized = ZERO
    pending = None
    fills = []
    signals = []
    daily = []

    for day in sessions:
        if pending is not None:
            buy = pending['side'] == 'buy'
            price = (money(day.open + terms.slippage_per_share, ROUND_CEILING) if buy
                     else money(day.open - terms.slippage_per_share, ROUND_FLOOR))
            budget = min(cash, terms.allocation)
            quantity = int(max(ZERO, budget - terms.fee) // price) if buy else shares
            gross = price * quantity
            cash_change = -gross - terms.fee if buy else gross - terms.fee
            pending['fill_session'] = day.session
            if quantity == 0:
                pending.update(status='skipped', reason='insufficient_cash' if cash < price + terms.fee else 'zero_shares')
            elif price <= ZERO:
                pending.update(status='skipped', reason='nonpositive_fill_price')
            elif cash + cash_change < ZERO:
                pending.update(status='skipped', reason='insufficient_cash_for_exit_fee')
            else:
                cash += cash_change
                trade_pnl = None
                if buy:
                    shares = quantity
                    entry_cost = -cash_change
                else:
                    shares = 0
                    trade_pnl = cash_change - entry_cost
                    realized += trade_pnl
                    entry_cost = ZERO
                pending['status'] = 'filled'
                fills.append({
                    'signal_session': pending['session'], 'fill_session': day.session,
                    'side': pending['side'], 'quantity': quantity,
                    'raw_open': str(day.open), 'price': str(price),
                    'fee': str(terms.fee), 'slippage_per_share': str(abs(price - day.open)),
                    'cash_change': str(cash_change), 'cash_after': str(cash),
                    'realized_pnl': str(trade_pnl) if trade_pnl is not None else None,
                })
            pending = None

        equity = money(cash + shares * day.close)
        daily.append({
            'session': day.session, 'close': str(day.close), 'shares': shares,
            'cash': str(cash), 'equity': str(equity), 'net_pnl': str(equity - terms.opening_cash),
        })

        if day.cross:
            buy = day.cross == 'up'
            signal = {'session': day.session, 'side': 'buy' if buy else 'sell', 'status': 'pending'}
            if buy and shares:
                signal.update(status='skipped', reason='already_long')
            elif not buy and not shares:
                signal.update(status='skipped', reason='flat_position')
            else:
                pending = signal
            signals.append(signal)

    return {
        'ledger_version': 'one-stock-price-return-v1',
        'terms': {name: str(value) for name, value in vars(terms).items()},
        'summary': {**daily[-1], 'realized_pnl': str(realized)},
        'signals': signals, 'fills': fills, 'daily': daily,
    }
