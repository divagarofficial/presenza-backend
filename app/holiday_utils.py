from __future__ import annotations

from datetime import date, datetime, timedelta


def _as_date(d) -> date | None:
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        # expects YYYY-MM-DD
        try:
            return datetime.fromisoformat(d).date()
        except Exception:
            return None
    return None


def is_holiday_active(today: date, holiday_date: date | None) -> bool:
    """Return True if holiday is active *until the end of the holiday_date day*.

    Semantics used across the app:
    - if admin declares holiday for 13th June 2026,
      it is active for the entire day of 13th June (i.e. up to 23:59)
      and becomes inactive at/after 14th June 00:00.

    With dates only, that maps to: today <= holiday_date.
    """
    if holiday_date is None:
        return False
    return today <= holiday_date


def holiday_end_timestamp(holiday_date: date) -> datetime:
    """Return an approximate end timestamp (23:59:59) for UI messaging."""
    return datetime.combine(holiday_date, datetime.max.time()).replace(microsecond=0)

