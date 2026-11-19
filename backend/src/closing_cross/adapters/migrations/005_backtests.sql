CREATE TABLE backtests (
    id INTEGER PRIMARY KEY,
    result_hash TEXT NOT NULL UNIQUE,
    report TEXT NOT NULL
);
