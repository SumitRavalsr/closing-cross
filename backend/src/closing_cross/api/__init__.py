import json
import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from closing_cross.adapters.database import connect
from closing_cross.adapters.paper import latest_ledgers

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
            connection.execute("SELECT 1 FROM verified_scans LIMIT 1").fetchone()
            connection.execute("SELECT 1 FROM paper_ledgers LIMIT 1").fetchone()
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


@app.get("/api/pilot/verified-scan")
def verified_scan() -> dict | None:
    with connect(readonly=True) as connection:
        row = connection.execute(
            "SELECT id, observed_at, report FROM verified_scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return {**json.loads(row["report"]), "id": row["id"], "observed_at": row["observed_at"]}


@app.get("/api/pilot/paper-ledgers")
def paper_ledgers() -> list[dict]:
    return latest_ledgers()
