CREATE TABLE forward_portfolio (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL
);

CREATE TABLE forward_sessions (
    session TEXT PRIMARY KEY,
    result TEXT NOT NULL
);

CREATE TABLE forward_attempts (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    target TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'complete', 'idle', 'failed')),
    detail TEXT
);
