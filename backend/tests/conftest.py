from datetime import date, datetime, timezone

import pytest

from app.providers.fixture import FixtureProvider
from app.services.instruments import get_instrument, get_listing
from app.services.snapshots import build_snapshot

# Saturday 7 Nov 2026, 11:30 IST. The last completed NSE session is Friday 6 Nov.
AS_OF = datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc)
END = date(2026, 11, 6)
INSTRUMENT_ID = "IN:INE002A01018"  # Reliance, core tier
EXTENDED_ID = "IN:INE509F01029"  # Cupid, extended tier (NSE listing only)


def make_snapshot(as_of: datetime = AS_OF, exchange: str = "NSE", instrument_id: str = INSTRUMENT_ID,
                  **provider_kwargs) -> dict:
    provider = FixtureProvider(end_date=provider_kwargs.pop("end_date", END), **provider_kwargs)
    inst = get_instrument(instrument_id)
    return build_snapshot(provider, inst, get_listing(inst, exchange), as_of)


@pytest.fixture
def snapshot():
    return make_snapshot()
