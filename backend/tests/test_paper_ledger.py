from decimal import Decimal

from fastapi.testclient import TestClient

from closing_cross.adapters.database import connect, migrate
from closing_cross.api import app
from closing_cross.domain.paper import PaperSession, PaperTerms, build_ledger
from closing_cross.scanner import seed_fixture


def test_fixture_round_trip_and_retry(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'pilot.sqlite3'))
    migrate()
    with TestClient(app) as client:
        assert client.get('/api/pilot/paper-ledgers').json() == []
        seed_fixture()
        saved = client.get('/api/pilot/paper-ledgers').json()
        seed_fixture()
        assert client.get('/api/pilot/paper-ledgers').json() == saved

    with connect(readonly=True) as connection:
        assert connection.execute('SELECT COUNT(*) FROM paper_ledgers').fetchone()[0] == 1

    ledger, = saved
    assert ledger['terms']['opening_cash'] == '1000.00'
    assert ledger['mode'] == 'fixture'
    buy, sell = ledger['fills']
    assert (buy['signal_session'], buy['fill_session'], buy['quantity']) == ('51', '52', 8)
    assert (buy['raw_open'], buy['price'], buy['fee'], buy['cash_change'], buy['cash_after']) == (
        '112', '113.00', '2.00', '-906.00', '94.00',
    )
    assert (sell['signal_session'], sell['fill_session'], sell['quantity']) == ('52', '53', 8)
    assert (sell['raw_open'], sell['price'], sell['fee'], sell['cash_change'], sell['cash_after']) == (
        '90', '89.00', '2.00', '710.00', '804.00',
    )
    assert ledger['daily'][-2]['equity'] == '734.00'
    assert ledger['summary'] == {
        'session': '53', 'close': '90', 'shares': 0, 'cash': '804.00',
        'equity': '804.00', 'net_pnl': '-196.00', 'realized_pnl': '-196.00',
    }


def test_pending_signal_and_unaffordable_fill():
    sessions = [PaperSession('2026-11-13', Decimal('100'), Decimal('100'), 'up')]
    terms = PaperTerms(allocation=Decimal('100.00'))
    result = build_ledger(sessions, terms)
    assert result['fills'] == []
    assert result['signals'][0]['status'] == 'pending'

    sessions.append(PaperSession('2026-11-16', Decimal('100'), Decimal('100'), 'down'))
    result = build_ledger(sessions, terms)
    assert result['fills'] == []
    assert [signal['reason'] for signal in result['signals']] == ['zero_shares', 'flat_position']
    assert result['summary']['cash'] == '1000.00'
