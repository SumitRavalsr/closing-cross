import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from closing_cross.domain.candles import DataError

IST = ZoneInfo('Asia/Kolkata')


@dataclass(frozen=True)
class TradingSession:
    day: date
    opens_at: datetime
    ready_at: datetime


def read_calendar(path: Path) -> tuple[list[TradingSession], str]:
    raw = path.read_bytes()
    try:
        contents = raw.decode('utf-8-sig')
    except UnicodeError:
        raise DataError('The forward calendar must be UTF-8 CSV') from None
    reader = csv.DictReader(io.StringIO(contents))
    if reader.fieldnames != ['session', 'open', 'ready']:
        raise DataError('Calendar headers must be session,open,ready')
    sessions = []
    for row in reader:
        try:
            day = date.fromisoformat(row['session'])
            opening = time.fromisoformat(row['open'])
            ready = time.fromisoformat(row['ready'])
            if opening.tzinfo or ready.tzinfo or ready <= opening or (sessions and day <= sessions[-1].day):
                raise ValueError
        except (TypeError, ValueError):
            raise DataError(f'Invalid or out-of-order calendar row at line {reader.line_num}') from None
        sessions.append(TradingSession(day, datetime.combine(day, opening, IST), datetime.combine(day, ready, IST)))
    if len(sessions) < 3:
        raise DataError('The calendar needs the seed, first forward session, and a following session')
    return sessions, hashlib.sha256(raw).hexdigest()
