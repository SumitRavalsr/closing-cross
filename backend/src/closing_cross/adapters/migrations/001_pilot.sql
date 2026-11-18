CREATE TABLE pilot_signals (
    symbol TEXT NOT NULL,
    session_number INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('up', 'down')),
    PRIMARY KEY (symbol, session_number)
);
