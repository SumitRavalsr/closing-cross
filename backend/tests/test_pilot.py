from fastapi.testclient import TestClient

from closing_cross.adapters.database import migrate
from closing_cross.api import app
from closing_cross.scanner import seed_fixture


def test_fixture_signals_are_visible_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "pilot.sqlite3"))
    client = TestClient(app)
    assert client.get("/api/ready").status_code == 503
    migrate()
    migrate()
    seed_fixture()
    seed_fixture()
    assert client.get("/api/ready").status_code == 200
    assert client.get("/api/pilot/signals").json() == [
        {"symbol": "FIXTURE", "session_number": 51, "direction": "up"},
        {"symbol": "FIXTURE", "session_number": 52, "direction": "down"},
    ]
