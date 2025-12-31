#presenza-backend/app/routes_admin.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Student
from app.schemas import StudentRegisterSchema
from app.dependencies import admin_required
from .models import SemesterSettings, Slot
from .schemas import SemesterCreateSchema, SlotCreateSchema
from .dependencies import admin_required
from .models import SemesterSettings
from .schemas import SemesterCreateSchema
from sqlalchemy import inspect, text
from app.models import QRSession
from app.utils.qr import generate_dynamic_qr, cleanup_old_qr
import secrets
from datetime import date
from sqlalchemy import func
from app.models import Student, DailyAttendance, SemesterSettings

from sqlalchemy import func
from app.models import Attendance, Timetable, Subject, TimeSlot

from sqlalchemy.orm import aliased
from sqlalchemy import func, distinct




router = APIRouter(prefix="/admin", tags=["Admin"])


# DB dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/students")
def register_student(
    data: StudentRegisterSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required)  # 🔐 Admin JWT check
):
    # check duplicate
    if db.query(Student).filter(Student.roll_number == data.roll_number).first():
        raise HTTPException(status_code=400, detail="Student already exists")

    student = Student(**data.dict())
    db.add(student)
    db.commit()
    db.refresh(student)

    return {
        "message": "Student registered successfully",
        "roll_number": student.roll_number
    }

@router.post("/semester")
def set_semester(
    data: SemesterCreateSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    db.query(SemesterSettings).filter(
        SemesterSettings.admin_id == admin["admin_id"]
    ).delete()

    semester = SemesterSettings(
        admin_id=admin["admin_id"],
        start_date=data.start_date,
        end_date=data.end_date
    )

    db.add(semester)
    db.commit()

    return {"message": "Semester duration set successfully"}

@router.post("/slots")
def create_slot(
    data: SlotCreateSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    if db.query(Slot).filter(Slot.slot_number == data.slot_number).first():
        raise HTTPException(status_code=400, detail="Slot already exists")

    slot = Slot(
        slot_number=data.slot_number,
        start_time=data.start_time,
        end_time=data.end_time
    )

    db.add(slot)
    db.commit()

    return {"message": f"Slot {data.slot_number} created successfully"}



@router.post("/semester/reset")
def reset_semester(
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    inspector = inspect(db.bind)

    tables_to_reset = [
        "daily_attendance",
        "attendance",
        "timetable",
        "subjects",
        "qr_sessions"
    ]

    for table in tables_to_reset:
        if inspector.has_table(table):
            db.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))

    db.commit()

    return {
        "message": "Semester reset successful. Students retained."
    }

@router.post("/qr/generate")
def generate_qr_for_slot(
    subject_code: str,
    slot_name: str,
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    # 1️⃣ Cleanup yesterday QR
    cleanup_old_qr(db)

    # 2️⃣ Check if QR already exists for today + slot
    existing = db.query(QRSession).filter(
        QRSession.admin_id == admin["admin_id"],
        QRSession.subject_code == subject_code,
        QRSession.slot_name == slot_name,
        QRSession.date == date.today()
    ).first()

    if not existing:
        secret = secrets.token_hex(16)

        qr_session = QRSession(
            admin_id=admin["admin_id"],
            subject_code=subject_code,
            slot_name=slot_name,
            secret=secret
        )
        db.add(qr_session)
        db.commit()
        db.refresh(qr_session)
    else:
        qr_session = existing

    # 3️⃣ Generate dynamic QR
    qr_value = generate_dynamic_qr(qr_session.secret)

    return {
        "slot": slot_name,
        "subject": subject_code,
        "qr": qr_value,
        "valid_for_seconds": 3
    }


@router.get("/dashboard/stats")
def admin_dashboard_stats(
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    today = date.today()

    # 1️⃣ Total students (admin scope)
    total_students = db.query(Student).filter(
        Student.department == admin["department"],
        Student.year == admin["year"],
        Student.section == admin["section"]
    ).count()

    # 2️⃣ Sections count (normally 1 for class admin)
    sections = db.query(
        Student.department,
        Student.year,
        Student.section
    ).distinct().count()

    # 3️⃣ Today attendance
    present_today = db.query(DailyAttendance).filter(
        DailyAttendance.date == today,
        DailyAttendance.status == "Present"
    ).count()

    total_marked_today = db.query(DailyAttendance).filter(
        DailyAttendance.date == today
    ).count()

    present_percent = (
        round((present_today / total_marked_today) * 100)
        if total_marked_today > 0 else 0
    )

    # 4️⃣ Pending OD
    pending_od = db.query(DailyAttendance).filter(
        DailyAttendance.status == "OD"
    ).count()

    # 5️⃣ Semester status
    semester = db.query(SemesterSettings).filter(
        SemesterSettings.admin_id == admin["admin_id"]
    ).first()

    semester_active = False
    days_left = None

    if semester:
        semester_active = semester.start_date <= today <= semester.end_date
        days_left = (semester.end_date - today).days

    return {
        "students": total_students,
        "sections": sections,
        "present_percent": present_percent,
        "pending_od": pending_od,
        "semester_active": semester_active,
        "days_left": days_left
    }


@router.get("/attendance/daily")
def get_daily_attendance(
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    today = date.today()

    students = db.query(Student).filter(
        Student.department == admin["department"],
        Student.year == admin["year"],
        Student.section == admin["section"]
    ).all()

    attendance_map = {
        a.student_id: a
        for a in db.query(DailyAttendance).filter(
            DailyAttendance.date == today
        ).all()
    }

    result = []

    for s in students:
        record = attendance_map.get(s.id)

        result.append({
            "roll": s.roll_number,
            "name": s.name,
            "status": record.status if record else "Absent",
            "source": record.source if record else "Not Marked"
        })

    return result


@router.get("/attendance/slots")
def get_slot_attendance(
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    today = date.today()

    data = db.query(
        Subject.name.label("subject"),
        TimeSlot.slot_name.label("slot"),
        func.count(Attendance.id).label("present")
    ).join(
        Timetable, Timetable.subject_id == Subject.id
    ).join(
        TimeSlot, Timetable.slot_id == TimeSlot.id
    ).outerjoin(
        Attendance,
        (Attendance.slot == TimeSlot.id) &
        (Attendance.date == today) &
        (Attendance.status == "PRESENT")
    ).filter(
        Timetable.admin_id == admin["admin_id"]
    ).group_by(
        Subject.name, TimeSlot.slot_name
    ).all()

    total_students = db.query(Student).filter(
        Student.department == admin["department"],
        Student.year == admin["year"],
        Student.section == admin["section"]
    ).count()

    return [
        {
            "subject": row.subject,
            "slot": row.slot,
            "present": row.present,
            "total": total_students
        }
        for row in data
    ]


@router.get("/attendance/report")
def attendance_report(
    db: Session = Depends(get_db),
    admin=Depends(admin_required)
):
    # 1️⃣ All students of admin's class
    students = db.query(Student).filter(
        Student.department == admin["department"],
        Student.year == admin["year"],
        Student.section == admin["section"]
    ).all()

    # 2️⃣ Total working days (distinct attendance dates)
    working_days = db.query(
        func.count(distinct(DailyAttendance.date))
    ).scalar() or 0

    report = []

    for s in students:
        present_days = db.query(DailyAttendance).filter(
            DailyAttendance.student_id == s.id,
            DailyAttendance.status == "Present"
        ).count()

        percentage = (
            round((present_days / working_days) * 100, 2)
            if working_days > 0 else 0
        )

        report.append({
            "roll": s.roll_number,
            "name": s.name,
            "working_days": working_days,
            "present_days": present_days,
            "percentage": percentage
        })

    return report
