import json
import sys
from datetime import date, timedelta
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from closing_cross.adapters.database import connect
from closing_cross.adapters.index_history import nifty_history
from closing_cross.api import app
from closing_cross.domain.candles import Candle
from closing_cross.scanner import main


def test_nifty_history_fills_missing_session_using_nse_mirror():
    first = date(2026, 10, 26)
    day = date(2026, 10, 27)
    requests = []

    def respond(request):
        requests.append(request.url.host)
        if request.url.host == 'www.nseindia.in':
            assert request.url.params['from'] == '26-10-2026'
            assert request.url.params['to'] == '27-10-2026'
            return httpx.Response(200, json={'data': [{
                'EOD_TIMESTAMP': '26-OCT-2026', 'EOD_INDEX_NAME': 'NIFTY 50', 'EOD_CLOSE_INDEX_VAL': 22753.2,
            }]})
        assert request.url.path.endswith('/ind_close_all_27102026.csv')
        if request.url.host == 'nsearchives.nseindia.com':
            return httpx.Response(403)
        return httpx.Response(200, text=(
            'Index Name,Index Date,Closing Index Value\n'
            'Nifty Next 50,27-10-2026,65000.00\nNifty 50,27-10-2026,22749.75\n'
        ))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert nifty_history(client, [first, day]) == {first: Decimal('22753.20'), day: Decimal('22749.75')}
    assert requests == ['www.nseindia.in', 'nsearchives.nseindia.com', 'archives.nseindia.com']


def test_portfolio_shares_cash_with_30_stocks_and_sells_before_buys(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'paper.sqlite3'))
    monkeypatch.setenv('PAPER_FEE', '2')
    monkeypatch.setenv('PAPER_SLIPPAGE_PER_SHARE', '1')
    watchlist = [f'TEST{i:02}' for i in range(30)]
    config = tmp_path / 'portfolio.json'
    config.write_text(json.dumps({'watchlist': watchlist}), encoding='utf-8')
    warmup = date(2026, 8, 3)
    dates = [warmup + timedelta(days=i) for i in range(80) if (warmup + timedelta(days=i)).weekday() < 5][:54]
    calls = []

    def read_many(_source, day, symbols):
        calls.append(day)
        index = dates.index(day)
        result = {}
        for symbol in symbols - {watchlist[-1]}:
            if symbol in watchlist[:7]:
                close = {50: 550, 51: 400}.get(index, 500)
            else:
                close = 550 if index == 51 else 500
            result[symbol] = Candle.parse(day, [500, 600, 350, close, 100], 'test')
        return result

    monkeypatch.setattr('closing_cross.scanner.portfolio.Bhavcopy.read_many', read_many)
    monkeypatch.setattr('closing_cross.scanner.portfolio.check_corporate_actions', lambda *args: None)
    index_closes = dict(zip(dates[50:], map(Decimal, ('100', '125', '100', '120')), strict=True))
    monkeypatch.setattr('closing_cross.scanner.portfolio.nifty_history', lambda http, days: index_closes)
    monkeypatch.setattr(sys, 'argv', [
        'closing-cross', 'backtest-portfolio', '--watchlist', str(config), '--from', str(dates[50]),
        '--through', str(dates[-1]), '--warmup-from', str(warmup),
    ])

    main()
    first = json.loads(capsys.readouterr().out)
    assert sorted(calls) == dates
    main()
    assert json.loads(capsys.readouterr().out)['id'] == first['id']
    with connect(readonly=True) as connection:
        assert connection.execute('SELECT COUNT(*) FROM backtests').fetchone()[0] == 1
    with TestClient(app) as client:
        report = client.get('/api/pilot/backtest').json()

    assert report['terms']['opening_cash'] == '10000.00'
    assert report['terms']['allocation'] == '2000.00'
    assert report['mode'] == 'portfolio_backtest'
    assert report['watchlist'] == watchlist
    assert report['excluded'][0]['symbol'] == watchlist[-1]
    assert [trade['symbol'] for trade in report['fills'] if trade['fill_session'] == str(dates[51])] == watchlist[:7]
    opening_fills = [trade for trade in report['fills'] if trade['fill_session'] == str(dates[52])]
    assert opening_fills[0]['side'] == 'sell'
    assert opening_fills[-1]['side'] == 'buy'
    assert all(float(row['cash']) >= 0 for row in report['daily'])
    assert len(report['stocks']) == 29
    assert any(stock['shares'] == 0 for stock in report['stocks'])
    assert any(signal.get('reason') == 'insufficient_cash' for signal in report['signals'])
    assert Decimal(report['benchmark']['return']) == Decimal('0.20')
    assert Decimal(report['benchmark']['max_drawdown']) == Decimal('0.20')
    assert [row['session'] for row in report['benchmark']['daily']] == [row['session'] for row in report['daily']]
    assert Decimal(report['summary']['total_fees']) == 2 * len(report['fills']) == first['fills'] * 2
    equity = [Decimal('10000'), *(Decimal(row['equity']) for row in report['daily'])]
    assert Decimal(report['summary']['return']) == equity[-1] / equity[0] - 1
    assert Decimal(report['summary']['max_drawdown']) == max(
        (max(equity[:i + 1]) - value) / max(equity[:i + 1]) for i, value in enumerate(equity)
    )
