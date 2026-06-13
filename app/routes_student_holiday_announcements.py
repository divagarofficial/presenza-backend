from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import student_required
from app.models import HolidayDeclaration

router = APIRouter(prefix="/students", tags=["Students"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/holiday/announcements")
def student_holiday_announcements(
    db: Session = Depends(get_db),
    user=Depends(student_required),
):
    """Return active holiday announcements for the student.

    HolidayDeclaration is date-only; it is considered active for the entire
    holiday_date (IST) and ends at 00:00 of the next day.

    With date-only fields, that is equivalent to: today <= holiday_date.
    """

    sid = user.get("student_id")
    if not sid:
        return {"announcements": []}

    # Find student's scope
    from app.models import Student

    student = db.query(Student).filter(Student.id == sid).first()
    if not student:
        return {"announcements": []}

    today = date.today()

    rows = (
        db.query(HolidayDeclaration)
        .filter(
            HolidayDeclaration.department == student.department,
            HolidayDeclaration.year == student.year,
            HolidayDeclaration.section == student.section,
            HolidayDeclaration.holiday_date >= today,
        )
        .order_by(HolidayDeclaration.holiday_date.desc())
        .all()
    )

    announcements = []
    for r in rows:
        end_date = r.holiday_date + timedelta(days=1)
        announcements.append(
            {
                "id": r.id,
                "holiday_date": r.holiday_date.isoformat(),
                # UI wants end time notionally at 12:00 AM of next day
                "active_until": end_date.isoformat(),
                "reason": r.reason,
            }
        )

    return {"announcements": announcements}

