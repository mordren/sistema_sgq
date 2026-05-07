import os
from datetime import datetime
from zoneinfo import ZoneInfo


BRASILIA_TZ = ZoneInfo(os.environ.get('APP_TIMEZONE', 'America/Sao_Paulo'))


def agora_brasilia() -> datetime:
    """Return current Brasilia time as a naive datetime for existing DB columns."""
    return datetime.now(BRASILIA_TZ).replace(tzinfo=None)
