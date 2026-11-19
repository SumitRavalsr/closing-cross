from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from closing_cross.adapters.backtest import check_corporate_actions, store_backtest
from closing_cross.adapters.database import connect, migrate
from closing_cross.api import app
from closing_cross.domain.candles import Candle, DataError
from closing_cross.domain.paper import PaperTerms
from closing_cross.scanner.backtest import backtest, load_history


def candles(closes):
    first = date(2026, 7, 1)
    return [Candle.parse(first + timedelta(days=i), [100, 120, 70, close, 100], 'test')
            for i, close in enumerate(closes)]


def test_funding_date_keeps_warmup_signals_out_of_positions(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'backtest.sqlite3'))
    migrate()
    history = candles([100] * 50 + [110, 110, 70, 100])
    terms = PaperTerms(opening_cash=Decimal('5000.00'), allocation=Decimal('5000.00'))
    report = backtest(history, 'RELIANCE', history[51].session, terms)
    assert report['warmup_sessions'] == 51
    assert report['fills'] == []
    assert all(row['action'] == 'hold_cash' for row in report['daily'])
    assert report['summary']['cash'] == '5000.00'

    first_id = store_backtest(report)
    assert store_backtest(report) == first_id
    with connect(readonly=True) as connection:
        assert connection.execute('SELECT COUNT(*) FROM backtests').fetchone()[0] == 1
    with TestClient(app) as api:
        assert api.get('/api/pilot/backtest').json() == {**report, 'id': first_id}


def test_backtest_reports_buy_sell_and_hold_with_costs():
    history = candles([100] * 50 + [110, 110, 70, 100])
    terms = PaperTerms(opening_cash=Decimal('5000.00'), allocation=Decimal('5000.00'))
    report = backtest(history, 'RELIANCE', history[50].session, terms)
    assert [row['action'] for row in report['daily']] == ['hold_cash', 'buy', 'hold_shares', 'sell']
    assert [fill['quantity'] for fill in report['fills']] == [49, 49]
    assert report['summary']['cash'] == '4898.00'
    assert report['summary']['net_pnl'] == '-102.00'


def test_backtest_calendar_requires_included_live_sunday_and_does_not_skip_a_missing_weekday():
    sunday, monday = date(2026, 11, 8), date(2026, 11, 9)

    class Exchange:
        def read(self, session, symbol):
            return Candle.parse(session, [100, 100, 100, 100, 10], 'test') if session == sunday else None

    with pytest.raises(DataError, match='No final traded NSE candle for 2026-11-09'):
        load_history(Exchange(), 'RELIANCE', sunday, monday, set(), {sunday})
    assert [c.session for c in load_history(Exchange(), 'RELIANCE', sunday, sunday, set(), {sunday})] == [sunday]


def test_nse_corporate_action_blocks_unadjusted_backtest():
    def respond(request):
        assert request.url.params['symbol'] == 'RELIANCE'
        assert request.url.params['from_date'] == '17-08-2026'
        return httpx.Response(200, json=[{
            'symbol': 'RELIANCE', 'series': 'EQ', 'subject': 'Bonus 1:1', 'exDate': '02-Nov-2026',
        }])

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(DataError, match='Unsupported corporate action'):
            check_corporate_actions(http, 'RELIANCE', date(2026, 8, 17), date(2026, 11, 19))
