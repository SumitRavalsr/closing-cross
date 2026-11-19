import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import pytest

from closing_cross.adapters.calendar import IST, read_calendar
from closing_cross.adapters.database import connect, migrate
from closing_cross.adapters.forward import status
from closing_cross.domain.candles import Candle, DataError
from closing_cross.domain.paper import PaperTerms
from closing_cross.scanner.forward import commit_session, initialize, run_forward


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'forward.sqlite3'))
    calendar = tmp_path / 'nse.csv'
    calendar.write_text(
        'session,open,ready\n' + ''.join(
            f'2026-11-{day},09:15,18:00\n' for day in (13, 16, 17, 18, 19, 20)
        ), encoding='utf-8',
    )
    migrate()
    seed = {
        'symbol': 'RELIANCE', 'session': '2026-11-13', 'token': '2885', 'strategy': '20-50-raw-v1',
        'candles': [{'close': '100'}] * 50,
    }
    with connect() as connection:
        connection.execute(
            'INSERT INTO verified_scans (input_hash, observed_at, report) VALUES (?, ?, ?)',
            ('seed', '2026-11-13T18:00:00+05:30', json.dumps(seed)),
        )
    initialize(calendar, date(2026, 11, 16), PaperTerms(), 'RELIANCE')
    candles = {
        date(2026, 11, day): Candle.parse(date(2026, 11, day), [opening, 120, 70, close, 100], 'test')
        for day, opening, close in [(16, 100, 110), (17, 112, 80), (18, 90, 90), (19, 90, 90)]
    }
    failures = set()
    requests = []

    class Broker:
        def __init__(self, http):
            pass

        def login(self):
            requests.append('login')
            if 'login' in failures:
                raise DataError('SmartAPI login failed (AB1050)')

        def resolve_equity(self, symbol):
            assert symbol == 'RELIANCE'
            return '2885'

        def daily(self, token, start, end):
            return {day: candle for day, candle in candles.items() if start <= day <= end}

    class Exchange:
        def __init__(self, http):
            pass

        def read(self, day, symbol):
            return None if day in failures else candles[day]

    monkeypatch.setattr('closing_cross.scanner.forward.SmartAPI', Broker)
    monkeypatch.setattr('closing_cross.scanner.forward.Bhavcopy', Exchange)
    return calendar, failures, requests


def scan(calendar: Path, day: int) -> dict:
    return run_forward(calendar, date(2026, 11, 20), clock=lambda: datetime(2026, 11, day, 18, tzinfo=IST))


def test_forward_recovers_preserves_timed_fills_and_retries_without_duplicates(pilot):
    calendar, failures, requests = pilot
    assert scan(calendar, 16)['processed'] == 1
    queued = status()['portfolio']['pending']
    assert queued['target_session'] == '2026-11-17'
    assert queued['observed_at'] == '2026-11-16T18:00:00+05:30'

    failures.add(date(2026, 11, 17))
    with pytest.raises(DataError, match='bhavcopy is missing'):
        scan(calendar, 17)
    assert status()['last_attempt']['status'] == 'failed'
    assert status()['portfolio']['pending'] == queued
    failures.clear()
    assert scan(calendar, 18)['processed'] == 2
    recovered = status()
    assert recovered['recent_sessions'][1]['fill']['price'] == '113.00'
    assert recovered['recent_sessions'][1]['mark']['equity'] == '734.00'
    assert recovered['recent_sessions'][0]['fill'] is None
    assert recovered['portfolio']['pending']['late'] is True
    assert recovered['portfolio']['pending']['target_session'] == '2026-11-19'

    assert scan(calendar, 19)['processed'] == 1
    final = status()
    assert final['portfolio']['cash'] == '804.00'
    assert final['recent_sessions'][0]['mark']['net_pnl'] == '-196.00'
    assert len([row['fill'] for row in final['recent_sessions'] if row['fill']]) == 2
    assert scan(calendar, 19)['status'] == 'idle'
    assert len(requests) == 4
    assert status()['recent_sessions'] == final['recent_sessions']


def test_late_entry_is_skipped_after_login_failure_and_missed_session(pilot):
    calendar, failures, _ = pilot
    failures.add('login')
    with pytest.raises(DataError, match='login failed'):
        scan(calendar, 16)
    assert status()['recent_sessions'] == []
    failures.clear()
    assert scan(calendar, 17)['processed'] == 2
    signals = status()['recent_sessions']
    assert signals[1]['signal']['reason'] == 'late_entry'
    assert signals[1]['signal']['late'] is True
    assert all(row['fill'] is None for row in signals)


def test_overlapping_forward_commits_finalize_one_session(pilot):
    path, _, _ = pilot
    calendar, digest = read_calendar(path)
    day = calendar[1].day
    candle = Candle.parse(day, [100, 120, 70, 110, 100], 'test')
    with ThreadPoolExecutor(max_workers=2) as executor:
        commits = [executor.submit(commit_session, candle, 1, calendar, calendar[1].ready_at, digest)
                   for _ in range(2)]
        assert sorted(commit.result() for commit in commits) == [False, True]
    assert len(status()['recent_sessions']) == 1
