from datetime import date
from decimal import Decimal

from closing_cross.domain.candles import Candle, DataError
from closing_cross.domain.paper import PaperPosition, PaperSession, PaperTerms, ZERO, money
from closing_cross.domain.strategy import crossover


def performance(values: list[Decimal], baseline: Decimal) -> dict[str, str]:
    peak = baseline
    drawdown = ZERO
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
    return {
        'return': str(values[-1] / baseline - 1),
        'max_drawdown': str(drawdown),
    }


def simulate_portfolio(history: dict[date, dict[str, Candle]], symbols: list[str], start: date, terms: PaperTerms) -> dict:
    cash = terms.opening_cash
    positions = {symbol: PaperPosition(ZERO) for symbol in symbols}
    closes: dict[str, list[Decimal]] = {symbol: [] for symbol in symbols}
    pending: dict[str, dict] = {}
    fills, signals, daily = [], [], []

    for session, candles in sorted(history.items()):
        for symbol in symbols:
            closes[symbol].append(candles[symbol].close)
        if session < start:
            continue
        if len(closes[symbols[0]]) < 51:
            raise DataError('Include at least 50 NSE sessions before the first funded session')

        label = session.isoformat()
        sessions = {
            symbol: PaperSession(label, candles[symbol].open, candles[symbol].close, crossover(closes[symbol]))
            for symbol in symbols
        }
        trades = []
        for side in ('sell', 'buy'):
            for symbol in symbols:
                signal = pending.get(symbol)
                if not signal or signal['side'] != side:
                    continue
                position = positions[symbol]
                position.cash = cash
                fill = position.settle_open(sessions[symbol], signal, terms)
                cash = position.cash
                if fill:
                    trades.append(symbol)
                    fills.append({'symbol': symbol, **fill})
        pending.clear()

        for symbol, position in positions.items():
            signal = position.signal_at_close(sessions[symbol])
            if signal:
                signal['symbol'] = symbol
                signals.append(signal)
                if signal['status'] == 'pending':
                    pending[symbol] = signal

        value = sum((money(position.shares * candles[symbol].close) for symbol, position in positions.items()), ZERO)
        equity = cash + value
        daily.append({
            'session': label, 'cash': str(cash), 'market_value': str(value), 'equity': str(equity),
            'net_pnl': str(equity - terms.opening_cash), 'open_positions': sum(p.shares > 0 for p in positions.values()),
            'fills': trades,
        })

    if not daily:
        raise DataError('The portfolio backtest has no funded sessions')
    actual = history[max(history)]
    stocks = []
    for symbol, position in positions.items():
        mark = money(position.shares * actual[symbol].close)
        stocks.append({
            'symbol': symbol, 'shares': position.shares, 'close': str(actual[symbol].close), 'market_value': str(mark),
            'cost_basis': str(position.entry_cost), 'realized_pnl': str(position.realized),
            'net_pnl': str(position.realized + mark - position.entry_cost),
        })
    realized = sum((p.realized for p in positions.values()), ZERO)
    return {
        'summary': {
            **daily[-1],
            **performance([Decimal(row['equity']) for row in daily], terms.opening_cash),
            'realized_pnl': str(realized),
            'unrealized_pnl': str(Decimal(daily[-1]['net_pnl']) - realized),
            'total_fees': str(sum((Decimal(fill['fee']) for fill in fills), ZERO)),
            'total_slippage': str(sum((abs(Decimal(fill['price']) - Decimal(fill['raw_open'])) * fill['quantity']
                                        for fill in fills), ZERO)),
        },
        'stocks': stocks, 'daily': daily, 'signals': signals, 'fills': fills,
    }
