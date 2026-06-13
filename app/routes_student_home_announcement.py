from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import student_required
from app.models import HolidayDeclaration, Student, SemesterSettings


router = APIRouter(prefix="/students", tags=["Students"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/home/announcements")
def student_home_announcements(
    db: Session = Depends(get_db),
    user=Depends(student_required),
):
    sid = user.get("student_id")
    if not sid:
        return {"announcements": []}

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
        # Show the soonest holiday first (closest to today)
        .order_by(HolidayDeclaration.holiday_date.asc())
        .all()
    )

    announcements = []
    for r in rows:
        announcements.append(
            {
                "type": "HOLIDAY",

                "holiday_date": r.holiday_date.isoformat(),
                "active_until": (r.holiday_date).isoformat(),
                "reason": r.reason,
            }
        )

    # Semester info from SemesterSettings (single row per admin_id; for student we take the first matching one)
    semester_end_date = None
    days_left = None
    try:
        sem = db.query(SemesterSettings).first()
        if sem and sem.end_date:
            semester_end_date = sem.end_date.isoformat()
            days_left = (sem.end_date - today).days
    except Exception:
        # keep home page working even if semester settings are missing
        pass

    return {
        "announcements": announcements,
        "semester_end_date": semester_end_date,
        "days_left": days_left,
    }


