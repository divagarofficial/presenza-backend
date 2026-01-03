#presenza-backend/app/routes_students.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt

from .database import SessionLocal
from .models import Student
from .schemas import StudentRegisterSchema, StudentLoginSchema
from .security import SECRET_KEY, ALGORITHM

from datetime import date
from .models import Attendance, QRSession, Student
from .dependencies import student_required
from app.utils.qr import validate_dynamic_qr
from app.utils.attendance import auto_mark_daily_attendance
from .models import DailyAttendance
from datetime import date
from sqlalchemy import func



router = APIRouter(prefix="/students", tags=["Students"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# STUDENT REGISTRATION
# --------------------------------------------------
@router.post("/register")
def register_student(
    data: StudentRegisterSchema,
    db: Session = Depends(get_db)
):
    existing = db.query(Student).filter(
        Student.roll_number == data.roll_number
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Student already exists")

    student = Student(
        roll_number=data.roll_number,
        name=data.name,
        department=data.department,
        year=data.year,
        section=data.section,
        mobile=data.mobile,
        is_cr=data.is_cr
    )

    db.add(student)
    db.commit()
    db.refresh(student)

    return {
        "message": "Student registered successfully",
        "roll_number": student.roll_number
    }


# --------------------------------------------------
# STUDENT LOGIN (ROLL NUMBER + MOBILE)
# --------------------------------------------------
@router.post("/login")
def student_login(
    data: StudentLoginSchema,
    db: Session = Depends(get_db)
):
    student = db.query(Student).filter(
        Student.roll_number == data.roll_number
    ).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Mobile number acts as password
    if student.mobile != data.mobile:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    payload = {
        "sub": student.roll_number,
        "role": "student",
        "exp": datetime.utcnow() + timedelta(hours=6)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@router.post("/scan-qr")
def scan_qr(
    qr_value: str,
    subject_code: str,
    slot_name: str,
    db: Session = Depends(get_db),
    student=Depends(student_required)
):
    # 1️⃣ Fetch QR session
    qr_session = db.query(QRSession).filter(
        QRSession.subject_code == subject_code,
        QRSession.slot_name == slot_name,
        QRSession.date == date.today()
    ).first()

    if not qr_session:
        raise HTTPException(status_code=404, detail="QR session not found")

    # 2️⃣ Validate QR
    if not validate_dynamic_qr(qr_session.secret, qr_value):
        raise HTTPException(status_code=401, detail="Invalid or expired QR")

    # 3️⃣ Prevent duplicate attendance
    already = db.query(Attendance).filter(
        Attendance.student_roll == student["roll_number"],
        Attendance.subject_code == subject_code,
        Attendance.slot_name == slot_name,
        Attendance.date == date.today()
    ).first()

    if already:
        raise HTTPException(status_code=409, detail="Attendance already marked")

    # 4️⃣ Mark attendance
    attendance = Attendance(
        student_roll=student["roll_number"],
        subject_code=subject_code,
        slot_name=slot_name
    )

    db.add(attendance)
    db.commit()
    auto_mark_daily_attendance(
    db=db,
    student_id=student.id,
    admin_id=admin["admin_id"]
)
    

    return {
        "message": "Attendance marked successfully",
        "subject": subject_code,
        "slot": slot_name
    }
@router.get("/student/me")
def get_my_profile(
    db: Session = Depends(get_db),
    user=Depends(student_required)  # JWT validation
):
    student = db.query(Student).filter(
        Student.id == user["student_id"]
    ).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return {
        "roll_number": student.roll_number,
        "name": student.name,
        "department": student.department,
        "year": student.year,
        "section": student.section,
        "mobile": student.mobile,
        "is_cr": student.is_cr
    }
# --------------------------------------------------
@router.get("/attendance/today")
def get_today_attendance(
    db: Session = Depends(get_db),
    student=Depends(student_required)
):
    record = db.query(DailyAttendance).filter(
        DailyAttendance.student_id == student["student_id"],
        DailyAttendance.date == date.today()
    ).first()

    if not record:
        return {
            "status": "Not Marked"
        }

    return {
        "status": record.status,
        "source": record.source
    }
# --------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/attendance/report")
def student_attendance_report(
    student=Depends(student_required),
    db: Session = Depends(get_db),
):
    student_id = student["student_id"]

    # 🔢 Total days attendance exists
    total_days = (
        db.query(func.count(func.distinct(DailyAttendance.date)))
        .scalar()
    )

    # ✅ Days present
    present_days = (
        db.query(DailyAttendance)
        .filter(
            DailyAttendance.student_id == student_id,
            DailyAttendance.status == "Present",
        )
        .count()
    )

    absent_days = total_days - present_days if total_days else 0

    percentage = (
        round((present_days / total_days) * 100, 2)
        if total_days > 0
        else 0
    )

    # 📅 Day-wise records
    records = (
        db.query(DailyAttendance)
        .filter(DailyAttendance.student_id == student_id)
        .order_by(DailyAttendance.date.desc())
        .all()
    )

    return {
        "summary": {
            "total_days": total_days,
            "present_days": present_days,
            "absent_days": absent_days,
            "percentage": percentage,
        },
        "records": [
            {
                "date": str(r.date),
                "status": r.status,
                "source": r.source,
            }
            for r in records
        ],
    }
# --------------------------------------------------
@router.get("/attendance/daily/report")
def student_daily_report(
    db: Session = Depends(get_db),
    student=Depends(student_required),
):
    # 1️⃣ TOTAL WORKING DAYS (GLOBAL – SAME AS BEFORE)
    total_days = (
        db.query(DailyAttendance.date)
        .distinct()
        .count()
    )

    # 2️⃣ STUDENT PRESENT DAYS (FIXED STATUS CASE)
    present_days = (
        db.query(DailyAttendance)
        .filter(
            DailyAttendance.student_id == student["student_id"],
            DailyAttendance.status == "PRESENT",  # ✅ FIX
        )
        .count()
    )
    # Absent days can be derived if needed
    absent_days: int = max(total_days - present_days, 0)


    # 3️⃣ ATTENDANCE %
    percentage = (
        round((present_days / total_days) * 100)
        if total_days > 0
        else 0
    )

    # 4️⃣ STUDENT HISTORY
    history = (
        db.query(DailyAttendance)
        .filter(DailyAttendance.student_id == student["student_id"])
        .order_by(DailyAttendance.date.desc())
        .all()
    )

    return {
        "total_days": total_days,
        "present_days": present_days,
        "percentage": percentage,
        "daily_history": [
            {
                "date": a.date.isoformat(),
                "status": a.status,
                "source": a.source,
            }
            for a in history
        ],
    }
# --------------------------------------------------

@router.get("/attendance/summary")
def student_attendance_summary(
    student = Depends(student_required),
    db: Session = Depends(get_db)
):
    TOTAL_WORKING_DAYS = 75
    MIN_REQUIRED_PRESENT = 57
    MAX_ALLOWED_ABSENT = TOTAL_WORKING_DAYS - MIN_REQUIRED_PRESENT  # 18

    # Count present days
    present_days = (
        db.query(func.count(DailyAttendance.id))
        .filter(
            DailyAttendance.student_id == student["student_id"],
            DailyAttendance.status == "Present"
        )
        .scalar()
    ) or 0

    # Absent days so far
    absent_days = TOTAL_WORKING_DAYS - present_days
    leave_remaining = MAX_ALLOWED_ABSENT - absent_days

    return {
        "total_days": TOTAL_WORKING_DAYS,
        "present_days": present_days,
        "absent_days": absent_days,
        "attendance_percent": round((present_days / TOTAL_WORKING_DAYS) * 100, 2),
        "leave_allowed": max(0, leave_remaining),
        "min_required_present": MIN_REQUIRED_PRESENT
    }