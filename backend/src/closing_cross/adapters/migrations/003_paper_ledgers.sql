CREATE TABLE paper_ledgers (
    id INTEGER PRIMARY KEY,
    input_hash TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK (mode IN ('fixture', 'verified_replay')),
    source_scan_id INTEGER REFERENCES verified_scans(id),
    ledger TEXT NOT NULL
);

CREATE INDEX paper_ledgers_mode_id ON paper_ledgers (mode, id);
