import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from closing_cross.adapters.database import connect

app = FastAPI(title="Closing Cross Pilot")


class Signal(BaseModel):
    symbol: str
    session_number: int
    direction: Literal["up", "down"]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ready")
def ready() -> dict[str, str]:
    try:
        with connect(readonly=True) as connection:
            connection.execute("SELECT 1 FROM pilot_signals LIMIT 1").fetchone()
    except sqlite3.Error as error:
        raise HTTPException(503, "Pilot database is unavailable") from error
    return {"status": "ready"}


@app.get("/api/pilot/signals", response_model=list[Signal])
def signals() -> list[Signal]:
    with connect(readonly=True) as connection:
        rows = connection.execute(
            "SELECT symbol, session_number, direction FROM pilot_signals ORDER BY session_number"
        ).fetchall()
    return [Signal(**dict(row)) for row in rows]
