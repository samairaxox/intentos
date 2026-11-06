from datetime import datetime,timezone,timedelta
from app.core.time import utc_iso


def test_database_timestamps_have_explicit_utc_offset():
    assert utc_iso(datetime(2026,11,6,5,0))=='2026-11-06T05:00:00+00:00'
    assert utc_iso(datetime(2026,11,6,10,30,tzinfo=timezone(timedelta(hours=5,minutes=30))))=='2026-11-06T05:00:00+00:00'
