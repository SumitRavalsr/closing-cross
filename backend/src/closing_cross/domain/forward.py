from datetime import datetime
from decimal import Decimal

from closing_cross.domain.candles import Candle, FIELDS
from closing_cross.domain.paper import PaperPosition, PaperSession, PaperTerms
from closing_cross.domain.strategy import crossover, moving_averages


def advance(
    state: dict, candle: Candle, observed: datetime, upcoming: list[datetime], calendar_hash: str,
) -> tuple[dict, dict]:
    terms = PaperTerms.parse([state['terms'][key] for key in ('opening_cash', 'allocation', 'fee', 'slippage_per_share')])
    position = PaperPosition(Decimal(state['cash']), state['shares'], Decimal(state['entry_cost']), Decimal(state['realized']))
    closes = [Decimal(close) for close in state['closes']] + [candle.close]
    day = PaperSession(candle.session.isoformat(), candle.open, candle.close, crossover(closes))
    fast, slow = moving_averages(closes)
    pending = state['pending'].copy() if state['pending'] else None
    settled = None
    fill = None
    if pending and pending['target_session'] == day.session:
        settled = pending
        fill = position.settle_open(day, settled, terms)
        pending = None
    if pending and pending['target_session'] is None:
        deferred = next((opening for opening in upcoming if opening > observed), None)
        if deferred:
            pending.update(target_session=deferred.date().isoformat(), target_open_at=deferred.isoformat())

    signal = position.signal_at_close(day)
    if signal:
        target = upcoming[0]
        signal.update(observed_at=observed.isoformat(), intended_session=target.date().isoformat(), late=observed >= target)
        if signal['status'] == 'pending':
            if pending:
                signal.update(status='skipped', reason='signal_already_pending')
            elif signal['late'] and signal['side'] == 'buy':
                signal.update(status='skipped', reason='late_entry')
            else:
                future = next((opening for opening in upcoming if opening > observed), None)
                if future is None:
                    signal.update(target_session=None, reason='awaiting_calendar')
                else:
                    signal.update(target_session=future.date().isoformat(), target_open_at=future.isoformat())
                pending = signal

    return {
        **state, 'last_session': day.session, 'closes': [str(close) for close in closes[-50:]],
        'cash': str(position.cash), 'shares': position.shares, 'entry_cost': str(position.entry_cost),
        'realized': str(position.realized), 'pending': pending,
    }, {
        'session': day.session, 'observed_at': observed.isoformat(), 'calendar_hash': calendar_hash,
        'candle': {key: str(getattr(candle, key)) for key in FIELDS},
        'sma20': str(fast), 'sma50': str(slow), 'cross': day.cross,
        'signal': signal, 'settled_signal': settled, 'fill': fill,
        'mark': {**position.mark_close(day, terms), 'realized_pnl': str(position.realized)},
    }
