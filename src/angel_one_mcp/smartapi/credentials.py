import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from angel_one_mcp.smartapi.errors import BrokerError


@dataclass(frozen=True, repr=False)
class AngelCredentials:
    api_key: str
    client_code: str
    pin: str
    totp_secret: str

    @classmethod
    def load(cls) -> 'AngelCredentials':
        name = os.environ.get('ANGEL_CREDENTIALS_FILE')
        if not name:
            raise BrokerError('Angel One credentials are not mounted. Configure ANGEL_CREDENTIALS_FILE on the server')
        try:
            with Path(name).open('rb') as source:
                mode = os.fstat(source.fileno()).st_mode
                if not stat.S_ISREG(mode) or (os.name != 'nt' and mode & 0o037):
                    raise ValueError
                raw = source.read(16_385)
            if len(raw) > 16_384:
                raise ValueError
            data = json.loads(raw)
            values = [data[key].strip() for key in ('api_key', 'client_code', 'pin', 'totp_secret')]
            if not all(value and value.isascii() and value.isprintable() for value in values):
                raise ValueError
        except (AttributeError, KeyError, OSError, TypeError, ValueError, RecursionError):
            raise BrokerError('Angel One credential file is unreadable, has unsafe permissions, or is invalid') from None
        return cls(*values)
