#prazenza-backend/app/utils/attendance.py
from datetime import date
from sqlalchemy.orm import Session

from app.models import Attendance, DailyAttendance, Timetable


def auto_mark_daily_attendance(
    db: Session,
    student_id: int,
    admin_id: str,
):
    """Auto-mark DailyAttendance as PRESENT only when all slot attendances are PRESENT.

    IMPORTANT:
    - In your flow, QR/manual slot scan calls this helper with admin_id=None.
    - In that case we must NOT auto-mark daily attendance, otherwise every full-slot scan
      could overwrite daily color/state unexpectedly after manual edits.
    """

    today = date.today()

    # If we don't know which admin's timetable to compare against, don't auto-mark.
    if not admin_id:
        return

    # 1️⃣ Total slots for today (from timetable)
    total_slots = db.query(Timetable).filter(Timetable.admin_id == admin_id).count()

    if total_slots == 0:
        return  # timetable not set

    # 2️⃣ Slots attended by student today (PRESENT only)
    attended_slots = db.query(Attendance).filter(
        Attendance.student_id == student_id,
        Attendance.date == today,
        Attendance.status == "PRESENT",
    ).count()

    # 3️⃣ Already marked daily?
    already = db.query(DailyAttendance).filter(
        DailyAttendance.student_id == student_id,
        DailyAttendance.date == today,
    ).first()

    # 4️⃣ Auto mark daily PRESENT only when all slots are PRESENT
    if attended_slots == total_slots and not already:
        daily = DailyAttendance(
            student_id=student_id,
            date=today,
            status="PRESENT",
            source="AUTO",
            location_verified=False,
        )
        db.add(daily)
        db.commit()

