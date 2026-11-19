import json
from datetime import datetime, timedelta, timezone

from closing_cross.adapters.database import connect
from closing_cross.domain.candles import DataError


def load_state() -> dict:
    with connect(readonly=True) as connection:
        row = connection.execute('SELECT state FROM forward_portfolio WHERE id = 1').fetchone()
    if row is None:
        raise DataError('Initialize the forward pilot from a verified NSE scan first')
    return json.loads(row['state'])


def start_attempt(now: datetime) -> int:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO forward_attempts (started_at, status) VALUES (?, 'running')", (now.isoformat(),),
        )
        return cursor.lastrowid


def finish_attempt(attempt: int, now: datetime, target: str | None, status: str, detail: str) -> None:
    with connect() as connection:
        connection.execute(
            'UPDATE forward_attempts SET finished_at = ?, target = ?, status = ?, detail = ? WHERE id = ?',
            (now.isoformat(), target, status, detail, attempt),
        )


def status() -> dict:
    with connect(readonly=True) as connection:
        connection.execute('BEGIN')
        state = connection.execute('SELECT state FROM forward_portfolio WHERE id = 1').fetchone()
        attempt = connection.execute('SELECT * FROM forward_attempts ORDER BY id DESC LIMIT 1').fetchone()
        sessions = connection.execute('SELECT result FROM forward_sessions ORDER BY session DESC LIMIT 10').fetchall()
    portfolio = json.loads(state['state']) if state else None
    if portfolio:
        portfolio.pop('closes')
    due = datetime.fromisoformat(portfolio['next_due_at']) if portfolio else None
    return {
        'portfolio': portfolio, 'last_attempt': dict(attempt) if attempt else None,
        'overdue': due is not None and datetime.now(timezone.utc) >= due + timedelta(minutes=30),
        'recent_sessions': [json.loads(row['result']) for row in sessions],
    }
