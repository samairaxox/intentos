from datetime import datetime,timezone


def utc_iso(value:datetime)->str:
    """SQLite drops tzinfo from UTC database timestamps; never emit ambiguous local times."""
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
