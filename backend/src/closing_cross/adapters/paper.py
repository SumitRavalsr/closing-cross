import hashlib
import json
from sqlite3 import Connection

from closing_cross.adapters.database import connect


def save_ledger(connection: Connection, ledger: dict, source_scan_id: int | None = None) -> int:
    mode = 'fixture' if source_scan_id is None else 'verified_replay'
    encoded = json.dumps({**ledger, 'mode': mode, 'source_scan_id': source_scan_id}, sort_keys=True)
    digest = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    connection.execute(
        'INSERT INTO paper_ledgers (input_hash, mode, source_scan_id, ledger) VALUES (?, ?, ?, ?) '
        'ON CONFLICT (input_hash) DO NOTHING', (digest, mode, source_scan_id, encoded),
    )
    return connection.execute('SELECT id FROM paper_ledgers WHERE input_hash = ?', (digest,)).fetchone()['id']


def latest_ledgers() -> list[dict]:
    with connect(readonly=True) as connection:
        rows = connection.execute(
            'SELECT id, ledger FROM paper_ledgers '
            'WHERE id IN (SELECT MAX(id) FROM paper_ledgers GROUP BY mode) '
            "ORDER BY mode = 'fixture', id DESC"
        ).fetchall()
    return [{**json.loads(row['ledger']), 'id': row['id']} for row in rows]
