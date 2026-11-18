import argparse
from decimal import Decimal

from closing_cross.adapters.database import connect, migrate
from closing_cross.domain.strategy import crossover


def seed_fixture() -> None:
    closes = [Decimal(100)] * 50 + [Decimal(110), Decimal(80)]
    with connect() as connection:
        for session_number in range(51, len(closes) + 1):
            direction = crossover(closes[:session_number])
            if direction:
                connection.execute(
                    """
                    INSERT INTO pilot_signals VALUES (?, ?, ?)
                    ON CONFLICT (symbol, session_number) DO NOTHING
                    """,
                    ("FIXTURE", session_number, direction),
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Closing crossover pilot")
    parser.add_argument("command", choices=("migrate", "seed-fixture"))
    arguments = parser.parse_args()
    if arguments.command == "migrate":
        migrate()
    else:
        seed_fixture()
