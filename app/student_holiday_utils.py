from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .models import HolidayDeclaration


def get_active_holidays_for_student(db: Session, *, department: str, year: str, section: str, today: date):
    """Return active holiday declarations for student scope.

    Holiday is active for the entire holiday_date day (inclusive), which with
    date-only comparison is equivalent to: today <= holiday_date.
    """

    rows = (
        db.query(HolidayDeclaration)
        .filter(
            HolidayDeclaration.department == department,
            HolidayDeclaration.year == year,
            HolidayDeclaration.section == section,
            HolidayDeclaration.holiday_date >= today,
        )
        .order_by(HolidayDeclaration.holiday_date.desc())
        .all()
    )

    out = []
    for r in rows:
        out.append(
            {
                "holiday_date": r.holiday_date.isoformat(),
                "reason": r.reason,
            }
        )

    # If multiple declarations exist, keep unique dates (latest first)
    seen = set()
    uniq = []
    for item in out:
        if item["holiday_date"] in seen:
            continue
        seen.add(item["holiday_date"])
        uniq.append(item)

    return uniq

