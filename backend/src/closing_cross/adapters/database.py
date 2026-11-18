import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from closing_cross.settings import database_path

MIGRATIONS = Path(__file__).with_name("migrations")


@contextmanager
def connect(*, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    path = database_path().resolve()
    if not readonly:
        path.parent.mkdir(parents=True, exist_ok=True)
    target = f"{path.as_uri()}?mode=ro" if readonly else str(path)
    with closing(sqlite3.connect(target, uri=readonly)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            yield connection


def migrate() -> None:
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            version = int(migration.stem.split("_", maxsplit=1)[0])
            if version > current:
                pending = ""
                for line in migration.read_text(encoding="utf-8").splitlines(keepends=True):
                    pending += line
                    if sqlite3.complete_statement(pending):
                        connection.execute(pending)
                        pending = ""
                if pending.strip():
                    raise sqlite3.OperationalError(f"Incomplete SQL in {migration.name}")
                connection.execute(f"PRAGMA user_version = {version}")
