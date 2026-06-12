#presenza-backend/app/routes_students.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt
from typing import Optional

from .database import SessionLocal
from .models import (
    AbsenceRequest,
    Admin,
    Attendance,
    DailyAttendance,
    GrievanceRequest,
    ODRequest,
    QRSession,
    Student,
    Subject,
    Timetable,
    TimeSlot,
)
from .schemas import StudentRegisterSchema, StudentLoginSchema
from .security import SECRET_KEY, ALGORITHM
from .dependencies import student_required
from app.utils.qr import validate_dynamic_qr
from app.utils.attendance import auto_mark_daily_attendance
from sqlalchemy import func

from .od_absence_history import (
    get_student_od_history,
    get_student_absence_history,
)


import os
from datetime import date
from fastapi import status

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
    roll = (data.roll_number or "").strip()
    mobile = (data.mobile or "").strip()

    student = db.query(Student).filter(Student.roll_number == roll).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if (student.mobile or "").strip() != mobile:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    payload = {
        "sub": student.roll_number,
        "role": "student",
        "student_id": student.id,
        "roll_number": student.roll_number,
        "is_cr": bool(student.is_cr),
        "exp": datetime.utcnow() + timedelta(hours=6),
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
    # auto marking based on slot attendance (if timetable is configured)
    auto_mark_daily_attendance(
        db=db,
        student_id=student["student_id"],
        admin_id=None,
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
        return {"status": "Not Marked"}

    return {"status": record.status, "source": record.source}


def _format_slot_status(raw: str | None) -> str:
    if not raw:
        return "Not Marked"
    u = raw.upper()
    if u == "PRESENT":
        return "Present"
    if u == "OD":
        return "OD"
    if u == "ABSENT":
        return "Absent"
    return raw


def _today_summary_label(slots: list[dict], daily_status: str) -> str:
    if not slots:
        return daily_status if daily_status != "Not Marked" else "No timetable"
    statuses = [s["status"] for s in slots]
    if all(s == "Present" for s in statuses):
        return "Present"
    if all(s == "OD" for s in statuses):
        return "OD"
    if all(s == "Absent" for s in statuses):
        return "Absent"
    if all(s in ("Present", "OD") for s in statuses) and any(
        s == "OD" for s in statuses
    ):
        return "In Progress"
    if any(s == "Not Marked" for s in statuses):
        return "In Progress"
    return "In Progress"


@router.get("/attendance/today/detail")
def get_today_attendance_detail(
    db: Session = Depends(get_db),
    student=Depends(student_required),
):
    sid = student.get("student_id")
    if not sid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please log in again",
        )

    stud = db.query(Student).filter(Student.id == sid).first()
    if not stud:
        raise HTTPException(status_code=404, detail="Student not found")

    today = date.today()
    daily_rec = (
        db.query(DailyAttendance)
        .filter(
            DailyAttendance.student_id == sid,
            DailyAttendance.date == today,
        )
        .first()
    )
    daily_status = "Not Marked"
    daily_source = None
    if daily_rec:
        daily_status = daily_rec.status
        daily_source = daily_rec.source

    admin = (
        db.query(Admin)
        .filter(
            Admin.department == stud.department,
            Admin.year == stud.year,
            Admin.section == stud.section,
        )
        .first()
    )

    slots_out: list[dict] = []
    if admin:
        weekday = today.strftime("%A")
        rows = (
            db.query(TimeSlot, Subject)
            .join(Timetable, Timetable.slot_id == TimeSlot.id)
            .join(Subject, Subject.id == Timetable.subject_id)
            .filter(
                Timetable.admin_id == admin.admin_id,
                Timetable.day == weekday,
            )
            .order_by(TimeSlot.slot_name)
            .all()
        )
        daily_is_od = bool(daily_rec and (daily_rec.status or "").upper() == "OD")
        daily_is_absent = bool(
            daily_rec and (daily_rec.status or "").strip().upper() == "ABSENT"
        )
        for ts, subject in rows:
            att = (
                db.query(Attendance)
                .filter(
                    Attendance.student_id == sid,
                    Attendance.date == today,
                    Attendance.slot == ts.id,
                )
                .first()
            )
            if att:
                st = _format_slot_status(att.status)
            elif daily_is_od:
                st = "OD"
            elif daily_is_absent:
                st = "Absent"
            else:
                st = "Not Marked"
            slots_out.append(
                {
                    "slot": ts.slot_name,
                    "subject": subject.name,
                    "status": st,
                }
            )

    summary = _today_summary_label(slots_out, daily_status)

    # Normalize status casing for frontend color logic
    # Normalize status casing for frontend color logic
    for s in slots_out:
        st = (s.get("status") or "").strip().lower()
        if st == "absent":
            s["status"] = "Absent"  # frontend expects "Absent"
        elif st == "present":
            s["status"] = "Present"
        elif st == "od":
            s["status"] = "OD"


    return {
        "daily": {"status": daily_status, "source": daily_source},
        "summary": summary,
        "slots": slots_out,
    }


# --------------------------------------------------
# OD APPLICATION (student)
# --------------------------------------------------
@router.post("/od/apply")
def apply_od(
    category: str = Form(...),
    slots: str | None = Form(None),
    reason: str = Form(...),
    proof: UploadFile = File(...),
    db: Session = Depends(get_db),
    student=Depends(student_required),
):
    if not student.get("student_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please log in again",
        )

    student_row = db.query(Student).filter(Student.id == student["student_id"]).first()

    if not student_row:
        raise HTTPException(status_code=404, detail="Student not found")

    category = category.upper().strip()
    if category not in ["FULL", "FULL_DAY", "SLOT"]:
        raise HTTPException(status_code=400, detail="Invalid OD category")

    normalized_category = "FULL_DAY" if category in ["FULL", "FULL_DAY"] else "SLOT"

    if normalized_category == "SLOT":
        if not slots or not slots.strip():
            raise HTTPException(status_code=400, detail="slots is required for SLOT category")
        slots_value = slots.strip()
    else:
        slots_value = None

    # Save proof under backend static folder
    proofs_dir = os.path.join(os.path.dirname(__file__), "static", "od_proofs")
    os.makedirs(proofs_dir, exist_ok=True)

    safe_name = proof.filename.replace("\\", "_").replace("/", "_")
    file_ext = os.path.splitext(safe_name)[1].lower()
    if file_ext not in [".pdf", ".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(status_code=400, detail="Unsupported proof file type")

    stored_name = f"od_{student_row.roll_number}_{int(datetime.utcnow().timestamp())}_{safe_name}"
    stored_path = os.path.join(proofs_dir, stored_name)

    content = proof.file.read()
    with open(stored_path, "wb") as f:
        f.write(content)

    proof_url = f"/static/od_proofs/{stored_name}"

    od = ODRequest(
        student_id=student_row.id,
        student_roll_number=student_row.roll_number,
        student_name=student_row.name,
        department=student_row.department,
        year=student_row.year,
        section=student_row.section,
        request_date=date.today(),
        category=normalized_category,
        slots=slots_value,
        reason=reason.strip(),
        proof_url=proof_url,
        proof_type=proof.content_type or file_ext,
        status="PENDING",
        cr_remarks=None,
    )

    db.add(od)
    db.commit()
    db.refresh(od)

    return {
        "message": "OD applied successfully",
        "od_request_id": od.id,
        "status": od.status,
    }


@router.post("/absent/declare")
def declare_absent(
    category: str = Form(...),
    slots: str | None = Form(None),
    reason: str = Form(...),
    proof: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    student=Depends(student_required),
):
    if not student.get("student_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please log in again",
        )

    student_row = db.query(Student).filter(Student.id == student["student_id"]).first()
    if not student_row:
        raise HTTPException(status_code=404, detail="Student not found")

    pending = (
        db.query(AbsenceRequest)
        .filter(
            AbsenceRequest.student_id == student_row.id,
            AbsenceRequest.request_date == date.today(),
            AbsenceRequest.status == "PENDING",
        )
        .first()
    )
    if pending:
        raise HTTPException(
            status_code=400,
            detail="You already have a pending absence request for today",
        )

    category = category.upper().strip()
    if category not in ["FULL", "FULL_DAY", "SLOT"]:
        raise HTTPException(status_code=400, detail="Invalid absence category")

    normalized_category = "FULL_DAY" if category in ["FULL", "FULL_DAY"] else "SLOT"

    if normalized_category == "SLOT":
        if not slots or not slots.strip():
            raise HTTPException(
                status_code=400,
                detail="slots is required for SLOT category",
            )
        slots_value = slots.strip()
    else:
        slots_value = None

    proof_url = None
    proof_type = None
    if proof is not None and getattr(proof, "filename", None) and str(proof.filename).strip():
        proofs_dir = os.path.join(os.path.dirname(__file__), "static", "absence_proofs")
        os.makedirs(proofs_dir, exist_ok=True)

        safe_name = proof.filename.replace("\\", "_").replace("/", "_")
        file_ext = os.path.splitext(safe_name)[1].lower()
        if file_ext not in [".pdf", ".png", ".jpg", ".jpeg", ".webp"]:
            raise HTTPException(status_code=400, detail="Unsupported proof file type")

        stored_name = (
            f"abs_{student_row.roll_number}_{int(datetime.utcnow().timestamp())}_{safe_name}"
        )
        stored_path = os.path.join(proofs_dir, stored_name)

        content = proof.file.read()
        with open(stored_path, "wb") as f:
            f.write(content)

        proof_url = f"/static/absence_proofs/{stored_name}"
        proof_type = proof.content_type or file_ext

    ab = AbsenceRequest(
        student_id=student_row.id,
        student_roll_number=student_row.roll_number,
        student_name=student_row.name,
        department=student_row.department,
        year=student_row.year,
        section=student_row.section,
        request_date=date.today(),
        category=normalized_category,
        slots=slots_value,
        reason=reason.strip(),
        proof_url=proof_url,
        proof_type=proof_type,
        status="PENDING",
        cr_remarks=None,
    )

    db.add(ab)
    db.commit()
    db.refresh(ab)

    return {
        "message": "Absence request submitted",
        "absence_request_id": ab.id,
        "status": ab.status,
    }





@router.get("/od/history")
def get_my_od_history(
    student=Depends(student_required),
    db: Session = Depends(get_db),
):
    student_id = student["student_id"]
    return {"requests": get_student_od_history(db, student_id)}


@router.get("/absent/history")
def get_my_absence_history(
    student=Depends(student_required),
    db: Session = Depends(get_db),
):
    student_id = student["student_id"]
    return {"requests": get_student_absence_history(db, student_id)}


@router.get("/grievances")
def get_my_grievances(
    student=Depends(student_required),
    db: Session = Depends(get_db),
):
    student_id = student["student_id"]
    grievances = (
        db.query(GrievanceRequest)
        .filter(GrievanceRequest.student_id == student_id)
        .order_by(GrievanceRequest.created_at.desc())
        .all()
    )

    def _display_status(value: str) -> str:
        if not value:
            return "Open"
        normalized = value.upper().replace(" ", "_")
        return {
            "OPEN": "Open",
            "UNDER_REVIEW": "Under Review",
            "RESOLVED": "Resolved",
            "REJECTED": "Rejected",
        }.get(normalized, value.title())

    return {
        "requests": [
            {
                "id": g.id,
                "request_date": str(g.request_date),
                "grievance_type": g.grievance_type,
                "slot": g.slot,
                "description": g.description,
                "proof_url": g.proof_url,
                "status": _display_status(g.status),
                "review_remarks": g.review_remarks,
            }
            for g in grievances
        ]
    }


@router.post("/grievances")
def submit_grievance(
    grievance_type: str = Form(...),
    request_date: date = Form(...),
    slot: str | None = Form(None),
    description: str = Form(...),
    proof: UploadFile = File(...),
    db: Session = Depends(get_db),
    student=Depends(student_required),
):
    if not student.get("student_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please log in again",
        )

    student_row = db.query(Student).filter(Student.id == student["student_id"]).first()
    if not student_row:
        raise HTTPException(status_code=404, detail="Student not found")

    allowed_types = {"DAILY", "SLOT", "OD", "OTHER"}
    normalized_type = grievance_type.strip().upper()
    if normalized_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid grievance type")

    if normalized_type == "SLOT" and (not slot or not slot.strip()):
        raise HTTPException(status_code=400, detail="Slot is required for slot grievances")

    proofs_dir = os.path.join(os.path.dirname(__file__), "static", "grievance_proofs")
    os.makedirs(proofs_dir, exist_ok=True)

    safe_name = proof.filename.replace("\\", "_").replace("/", "_")
    file_ext = os.path.splitext(safe_name)[1].lower()
    if file_ext not in [".pdf", ".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(status_code=400, detail="Unsupported proof file type")

    stored_name = f"grievance_{student_row.roll_number}_{int(datetime.utcnow().timestamp())}_{safe_name}"
    stored_path = os.path.join(proofs_dir, stored_name)

    content = proof.file.read()
    with open(stored_path, "wb") as f:
        f.write(content)

    proof_url = f"/static/grievance_proofs/{stored_name}"

    grievance = GrievanceRequest(
        student_id=student_row.id,
        student_roll_number=student_row.roll_number,
        student_name=student_row.name,
        department=student_row.department,
        year=student_row.year,
        section=student_row.section,
        request_date=request_date,
        grievance_type=normalized_type,
        slot=slot.strip() if slot else None,
        description=description.strip(),
        proof_url=proof_url,
        proof_type=proof.content_type or file_ext,
        status="OPEN",
        review_remarks=None,
    )

    db.add(grievance)
    db.commit()
    db.refresh(grievance)

    # Notification: inform admins of this student's section
    try:
        from app.notifications_utils import create_notification_for_admin

        create_notification_for_admin(
            db,
            target_department=student_row.department,
            target_year=student_row.year,
            target_section=student_row.section,
            message=f"A grievance was submitted for {student_row.roll_number}",
            notification_type="GRIEVANCE_SUBMITTED",
            meta={
                "grievance_id": grievance.id,
                "student_roll_number": student_row.roll_number,
                "type": normalized_type,
                "slot": slot,
            },
        )
    except Exception:
        pass

    return {
        "message": "Grievance submitted successfully",
        "grievance_id": grievance.id,
        "status": "Open",
    }



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
    # 1️⃣ TOTAL WORKING DAYS (GLOBAL – based on days where student has any daily record)
    total_days = (
        db.query(DailyAttendance.date)
        .filter(DailyAttendance.student_id == student["student_id"])
        .distinct()
        .count()
    )

    # 2️⃣ STUDENT PRESENT DAYS (ONLY PRESENT)
    present_days = (
        db.query(DailyAttendance)
        .filter(
            DailyAttendance.student_id == student["student_id"],
            DailyAttendance.status == "PRESENT",
        )
        .count()
    )

    # 3️⃣ ATTENDANCE %
    percentage = (
        round((present_days / total_days) * 100) if total_days > 0 else 0
    )

    # 4️⃣ STUDENT HISTORY (normalize casing to match frontend color logic)
    history = (
        db.query(DailyAttendance)
        .filter(DailyAttendance.student_id == student["student_id"])
        .order_by(DailyAttendance.date.desc())
        .all()
    )

    def _display_status(raw: str | None) -> str:
        if not raw:
            return "Not Marked"
        u = raw.strip().upper()
        return {
            "PRESENT": "Present",
            "ABSENT": "Absent",
            "OD": "OD",
        }.get(u, raw)

    return {
        "total_days": total_days,
        "present_days": present_days,
        "percentage": percentage,
        "daily_history": [
            {
                "date": a.date.isoformat(),
                "status": _display_status(a.status),
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
            DailyAttendance.status == "PRESENT"
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