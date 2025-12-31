#prazenza-backend/app/utils/attendance.py
from datetime import date
from sqlalchemy.orm import Session

from app.models import Attendance, DailyAttendance, Timetable, Student


def auto_mark_daily_attendance(
    db: Session,
    student_id: int,
    admin_id: str
):
    today = date.today()

    # 1️⃣ Total slots for today (from timetable)
    total_slots = db.query(Timetable).filter(
        Timetable.admin_id == admin_id
    ).count()

    if total_slots == 0:
        return  # timetable not set

    # 2️⃣ Slots attended by student today
    attended_slots = db.query(Attendance).filter(
        Attendance.student_id == student_id,
        Attendance.date == today,
        Attendance.status == "PRESENT"
    ).count()

    # 3️⃣ Already marked daily?
    already = db.query(DailyAttendance).filter(
        DailyAttendance.student_id == student_id,
        DailyAttendance.date == today
    ).first()

    # 4️⃣ Auto mark
    if attended_slots == total_slots and not already:
        daily = DailyAttendance(
            student_id=student_id,
            date=today,
            status="PRESENT",
            source="AUTO",
            location_verified=False
        )
        db.add(daily)
        db.commit()
