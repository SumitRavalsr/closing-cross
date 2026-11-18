import os
from pathlib import Path


def database_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH", "scanner.sqlite3"))
