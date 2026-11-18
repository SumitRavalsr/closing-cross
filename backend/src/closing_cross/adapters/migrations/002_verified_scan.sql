CREATE TABLE verified_scans (
    id INTEGER PRIMARY KEY,
    input_hash TEXT NOT NULL UNIQUE,
    observed_at TEXT NOT NULL,
    report TEXT NOT NULL
);
