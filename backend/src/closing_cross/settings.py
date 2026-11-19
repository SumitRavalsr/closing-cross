import os
from pathlib import Path

from closing_cross.domain.paper import PaperTerms


def database_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH", "scanner.sqlite3"))


def paper_terms() -> PaperTerms:
    return PaperTerms.parse([
        os.environ.get('PAPER_OPENING_CASH', '1000.00'),
        os.environ.get('PAPER_ALLOCATION', '1000.00'),
        os.environ.get('PAPER_FEE', '2.00'),
        os.environ.get('PAPER_SLIPPAGE_PER_SHARE', '1.00'),
    ])
