# presenza-backend/app/routes_cr.py

from fastapi import APIRouter, Depends, HTTPException, Form, Body
from sqlalchemy.orm import Session
from datetime import date, datetime
from io import BytesIO
import os
import pytz

from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

from app.database import SessionLocal
from app.models import (
    AbsenceRequest,
    Admin,
    Attendance,
    DailyAttendance,
    GrievanceRequest,
    ODRequest,
    Student,
    Subject,
    Timetable,
    TimeSlot,
)
from app.dependencies import cr_required, student_required
from app.schemas import (
    DailyAttendanceScanSchema,
    CRManualAttendanceBulkSchema,
    CRAttendanceEditBulkSchema,
    CRManualAttendanceBulkSchema,
    GrievanceDecisionSchema,
)

from app.notifications_utils import create_notification_for_student



router = APIRouter(prefix="/cr", tags=["Class Representative"])

IST = pytz.timezone("Asia/Kolkata")


# ===================== DB =====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _apply_od_slot_attendance(db: Session, od: ODRequest, admin: Admin) -> None:
    """Upsert per-slot attendance as OD (Attendance.slot stores TimeSlot.id)."""
    weekday = od.request_date.strftime("%A")
    base_q = (
        db.query(TimeSlot)
        .join(Timetable, Timetable.slot_id == TimeSlot.id)
        .filter(
            Timetable.admin_id == admin.admin_id,
            Timetable.day == weekday,
        )
    )
    if od.category == "FULL_DAY":
        time_slots = base_q.all()
    else:
        names = {s.strip() for s in (od.slots or "").split(",") if s.strip()}
        time_slots = [ts for ts in base_q.all() if ts.slot_name in names]

    for ts in time_slots:
        row = (
            db.query(Attendance)
            .filter(
                Attendance.student_id == od.student_id,
                Attendance.date == od.request_date,
                Attendance.slot == ts.id,
            )
            .first()
        )
        if row:
            row.status = "OD"
        else:
            db.add(
                Attendance(
                    student_id=od.student_id,
                    date=od.request_date,
                    slot=ts.id,
                    status="OD",
                )
            )


def _apply_absent_slot_attendance(db: Session, req: AbsenceRequest, admin: Admin) -> None:
    """Upsert per-slot attendance as ABSENT (Attendance.slot stores TimeSlot.id)."""
    weekday = req.request_date.strftime("%A")
    base_q = (
        db.query(TimeSlot)
        .join(Timetable, Timetable.slot_id == TimeSlot.id)
        .filter(
            Timetable.admin_id == admin.admin_id,
            Timetable.day == weekday,
        )
    )
    if req.category == "FULL_DAY":
        time_slots = base_q.all()
    else:
        names = {s.strip() for s in (req.slots or "").split(",") if s.strip()}
        time_slots = [ts for ts in base_q.all() if ts.slot_name in names]

    for ts in time_slots:
        row = (
            db.query(Attendance)
            .filter(
                Attendance.student_id == req.student_id,
                Attendance.date == req.request_date,
                Attendance.slot == ts.id,
            )
            .first()
        )
        if row:
            row.status = "ABSENT"
        else:
            db.add(
                Attendance(
                    student_id=req.student_id,
                    date=req.request_date,
                    slot=ts.id,
                    status="ABSENT",
                )
            )


# ===================== HELPERS =====================
def to_ist(dt: datetime | None):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(IST)
def draw_watermark(c, width, height):
    if os.path.exists(PRESENZA_LOGO):
        c.saveState()
        c.setFillAlpha(0.08)
        c.drawImage(
            PRESENZA_LOGO,
            width / 2 - 6 * cm,
            height / 2 - 6 * cm,
            width=12 * cm,
            height=12 * cm,
            mask="auto",
        )
        c.restoreState()


def draw_header(c, width, height, title, cr_student, today):
    draw_watermark(c, width, height)

    if os.path.exists(MINDURA_LOGO):
        c.drawImage(
            MINDURA_LOGO,
            width / 2 - 1.5 * cm,
            height - 3 * cm,
            width=3 * cm,
            height=3 * cm,
            mask="auto",
        )

    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, height - 3.6 * cm, "MINDURA TECHNOLOGIES")

    y = height - 5 * cm
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, title)

    y -= 1 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, f"Department : {cr_student.department}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Year / Section : {cr_student.year} {cr_student.section}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Date : {today.strftime('%d-%m-%Y')}")

    return y - 1 * cm


def draw_footer(c, width):
    c.setFont("Helvetica", 9)
    c.drawCentredString(
        width / 2,
        2.6 * cm,
        f"Report generated on : {to_ist(datetime.now()).strftime('%d-%m-%Y %I:%M %p')}",
    )
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(width / 2, 2.0 * cm, "MINDURA TECHNOLOGIES")
    c.setFont("Helvetica", 9)
    c.drawCentredString(
        width / 2,
        1.4 * cm,
        "© 2026 MINDURA TECHNOLOGIES. All rights reserved.",
    )
# ===================== ASSETS =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

MINDURA_LOGO = os.path.join(ASSETS_DIR, "mindura_logo.png")
PRESENZA_LOGO = os.path.join(ASSETS_DIR, "presenza_logo.png")


# ===================== SCAN =====================
@router.post("/attendance/daily/scan")
def mark_daily_attendance(
    data: DailyAttendanceScanSchema,
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="Only CR allowed")

    student = db.query(Student).filter(
        Student.roll_number == data.student_roll
    ).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    existing = db.query(DailyAttendance).filter(
        DailyAttendance.student_id == student.id,
        DailyAttendance.date == date.today(),
    ).first()

    if existing:
        return {"message": "Attendance already marked"}

    attendance = DailyAttendance(
        student_id=student.id,
        date=date.today(),
        status="PRESENT",
        source="CR SCAN",
        marked_by=cr["student_id"],
    )

    db.add(attendance)
    db.commit()

    try:
        create_notification_for_student(
            db,
            student_id=student.id,
            message=f"Daily attendance marked: Present ({date.today().isoformat()})",
            notification_type="ATTENDANCE_MARKED",
            meta={"date": date.today().isoformat(), "status": "Present", "source": "CR SCAN"},
        )
    except Exception:
        pass

    return {"message": "Attendance marked successfully"}


# ===================== MANUAL BULK ATTENDANCE =====================

@router.post("/attendance/daily/manual/bulk")
def cr_manual_bulk_attendance(
    data: CRManualAttendanceBulkSchema,
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    # 🔐 CR ONLY
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    today = date.today()

    cr_student = db.query(Student).filter(
        Student.id == cr["student_id"]
    ).first()

    if not cr_student:
        raise HTTPException(status_code=404, detail="CR not found")

    if not data.records:
        raise HTTPException(
            status_code=400,
            detail="No attendance records submitted"
        )

    # Map roll_number → status (ONLY PRESENT / OD)
    submitted = {
        r.roll_number: r.status.upper()
        for r in data.records
        if r.status.upper() in ["PRESENT", "OD"]
    }

    students = db.query(Student).filter(
        Student.department == cr_student.department,
        Student.year == cr_student.year,
        Student.section == cr_student.section,
    ).all()

    for student in students:
        # ❌ DO NOTHING for absentees
        if student.roll_number not in submitted:
            continue

        status = submitted[student.roll_number]

        existing = db.query(DailyAttendance).filter(
            DailyAttendance.student_id == student.id,
            DailyAttendance.date == today,
        ).first()

        if existing:
            existing.status = status
            existing.source = "CR MANUAL"
        else:
            db.add(DailyAttendance(
                student_id=student.id,
                date=today,
                status=status,
                source="CR MANUAL",
            ))

    # collect affected roll numbers so we can notify only those
    affected_students = [
        s
        for s in students
        if s.roll_number in submitted
    ]

    db.commit()

    # notify affected students (Present/OD only; absentees are inferred elsewhere)
    try:
        for s in affected_students:
            st = submitted.get(s.roll_number)
            create_notification_for_student(
                db,
                student_id=s.id,
                message=f"Daily attendance updated by CR ({date.today().isoformat()}): {st.title()}",
                notification_type="ATTENDANCE_MARKED",
                meta={"date": date.today().isoformat(), "status": st, "source": "CR MANUAL"},
            )
    except Exception:
        pass

    return {
        "message": "Manual attendance submitted successfully",
        "present": sum(1 for s in submitted.values() if s == "PRESENT"),
        "od": sum(1 for s in submitted.values() if s == "OD"),
    }


# ===================== STUDENT LIST FOR MANUAL ATTENDANCE =====================

@router.get("/attendance/daily/edit/students")
def get_students_for_daily_attendance_edit(
    date: str,
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    try:
        selected_date = datetime.strptime(date, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    cr_student = db.query(Student).filter(Student.id == cr["student_id"]).first()
    if not cr_student:
        raise HTTPException(status_code=404, detail="CR not found")

    students = (
        db.query(Student)
        .filter(
            Student.department == cr_student.department,
            Student.year == cr_student.year,
            Student.section == cr_student.section,
        )
        .order_by(Student.roll_number)
        .all()
    )

    present_rows = (
        db.query(DailyAttendance)
        .filter(DailyAttendance.date == selected_date)
        .join(Student, DailyAttendance.student_id == Student.id)
        .filter(
            Student.department == cr_student.department,
            Student.year == cr_student.year,
            Student.section == cr_student.section,
        )
        .all()
    )

    status_by_student_id = {r.student_id: (r.status or "ABSENT").upper() for r in present_rows}

    return {
        "date": selected_date.isoformat(),
        "students": [
            {
                "roll_number": s.roll_number,
                "name": s.name,
                "status": status_by_student_id.get(s.id, "ABSENT"),
            }
            for s in students
        ],
    }


@router.post("/attendance/daily/edit/bulk")
def cr_daily_edit_attendance_bulk(
    data: CRAttendanceEditBulkSchema,
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    cr_student = db.query(Student).filter(Student.id == cr["student_id"]).first()
    if not cr_student:
        raise HTTPException(status_code=404, detail="CR not found")

    if not data.records:
        raise HTTPException(status_code=400, detail="No attendance records submitted")

    allowed = {"PRESENT", "OD", "ABSENT"}
    submitted = {}
    for r in data.records:
        st = (r.status or "").upper().strip()
        if st not in allowed:
            raise HTTPException(status_code=400, detail=f"Invalid status for roll {r.roll_number}: {r.status}")
        submitted[r.roll_number] = st

    students = db.query(Student).filter(
        Student.department == cr_student.department,
        Student.year == cr_student.year,
        Student.section == cr_student.section,
    ).all()

    roll_to_student_id = {s.roll_number: s.id for s in students}

    for roll_number, status in submitted.items():
        sid = roll_to_student_id.get(roll_number)
        if not sid:
            continue

        existing = db.query(DailyAttendance).filter(
            DailyAttendance.student_id == sid,
            DailyAttendance.date == data.date,
        ).first()

        if existing:
            existing.status = status
            existing.source = "CR EDIT"
            existing.marked_by = cr["student_id"]
        else:
            db.add(
                DailyAttendance(
                    student_id=sid,
                    date=data.date,
                    status=status,
                    source="CR EDIT",
                    marked_by=cr["student_id"],
                )
            )

    db.commit()

    return {
        "message": "Attendance updated successfully",
        "date": data.date.isoformat(),
        "updated": len(submitted),
    }


@router.get("/attendance/daily/manual/students")
def get_students_for_manual_attendance(

    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    cr_student = db.query(Student).filter(
        Student.id == cr["student_id"]
    ).first()

    students = db.query(Student).filter(
        Student.department == cr_student.department,
        Student.year == cr_student.year,
        Student.section == cr_student.section,
    ).order_by(Student.roll_number).all()

    return {
        "date": date.today().strftime("%d-%m-%Y"),
        "students": [
            {
                "roll_number": s.roll_number,
                "name": s.name
            }
            for s in students
        ]
    }


# ===================== PRESENT LIST =====================
@router.get("/attendance/daily/today")
def get_today_present(
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    today = date.today()

    cr_student = db.query(Student).filter(
        Student.id == cr["student_id"]
    ).first()

    records = (
        db.query(DailyAttendance, Student)
        .join(Student, DailyAttendance.student_id == Student.id)
        .filter(
            DailyAttendance.date == today,
            Student.department == cr_student.department,
            Student.year == cr_student.year,
            Student.section == cr_student.section,
        )
        .order_by(DailyAttendance.created_at)
        .all()
    )

    return {
        "scanned": [
            {
                "roll_number": s.roll_number,
                "name": s.name,
                "time": to_ist(a.created_at).strftime("%I:%M %p"),
            }
            for a, s in records
        ]
    }


# ===================== ABSENT LIST =====================
@router.get("/attendance/daily/absent")
def get_today_absent(
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    today = date.today()

    cr_student = db.query(Student).filter(
        Student.id == cr["student_id"]
    ).first()

    present_ids = (
        db.query(DailyAttendance.student_id)
        .filter(DailyAttendance.date == today)
        .subquery()
    )

    absentees = (
        db.query(Student)
        .filter(
            Student.department == cr_student.department,
            Student.year == cr_student.year,
            Student.section == cr_student.section,
            ~Student.id.in_(present_ids),
        )
        .order_by(Student.roll_number)
        .all()
    )

    return {
        "absent": [
            {"roll_number": s.roll_number, "name": s.name}
            for s in absentees
        ]
    }


# ===================== CR DASHBOARD =====================
@router.get("/od/pending")
def get_pending_od_requests(
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="Only CR allowed")

    cr_student = db.query(Student).filter(Student.id == cr["student_id"]).first()
    if not cr_student:
        raise HTTPException(status_code=404, detail="CR not found")

    pending = (
        db.query(ODRequest)
        .filter(
            ODRequest.status == "PENDING",
            ODRequest.department == cr_student.department,
            ODRequest.year == cr_student.year,
            ODRequest.section == cr_student.section,
        )
        .order_by(ODRequest.created_at.desc())
        .all()
    )

    return {
        "requests": [
            {
                "id": r.id,
                "roll": r.student_roll_number,
                "name": r.student_name,
                "category": r.category,
                "slots": r.slots,
                "date": r.request_date.isoformat(),
                "reason": r.reason,
                "proof_url": r.proof_url,
                "proof_type": r.proof_type,
                "status": r.status,
                "cr_remarks": r.cr_remarks,
            }
            for r in pending
        ]
    }


@router.post("/od/{od_request_id}/decision")
def decide_od_request(
    od_request_id: int,
    decision: str = Form(...),
    remarks: str | None = Form(None),
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="Only CR allowed")

    cr_student = db.query(Student).filter(Student.id == cr["student_id"]).first()
    if not cr_student:
        raise HTTPException(status_code=404, detail="CR not found")

    od = db.query(ODRequest).filter(ODRequest.id == od_request_id).first()
    if not od:
        raise HTTPException(status_code=404, detail="OD request not found")

    # ensure belongs to same section
    if not (
        od.department == cr_student.department
        and od.year == cr_student.year
        and od.section == cr_student.section
    ):
        raise HTTPException(status_code=403, detail="Not in your section")

    decision_norm = decision.upper().strip()
    if decision_norm not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Invalid decision")

    od.status = decision_norm
    od.cr_remarks = remarks.strip() if remarks else None

    if decision_norm == "APPROVED":
        admin = (
            db.query(Admin)
            .filter(
                Admin.department == od.department,
                Admin.year == od.year,
                Admin.section == od.section,
            )
            .first()
        )
        if admin:
            _apply_od_slot_attendance(db, od, admin)

        # Full-day OD also updates consolidated daily row; slot-only OD is per-slot only.
        if od.category == "FULL_DAY":
            existing = db.query(DailyAttendance).filter(
                DailyAttendance.student_id == od.student_id,
                DailyAttendance.date == od.request_date,
            ).first()

            if existing:
                existing.status = "OD"
                existing.source = "CR OD"
                existing.marked_by = cr["student_id"]
            else:
                db.add(
                    DailyAttendance(
                        student_id=od.student_id,
                        date=od.request_date,
                        status="OD",
                        source="CR OD",
                        marked_by=cr["student_id"],
                    )
                )

    # notify the student for both APPROVED and REJECTED (user requested APPROVED + REJECTED)
    try:
        create_notification_for_student(
            db,
            student_id=od.student_id,
            message=f"OD request {decision_norm.title()} ({od.request_date.isoformat()})",
            notification_type="OD_APPROVED" if decision_norm == "APPROVED" else "OD_REJECTED",
            meta={
                "od_request_id": od.id,
                "date": od.request_date.isoformat(),
                "category": od.category,
                "slots": od.slots,
                "cr_remarks": od.cr_remarks,
            },
        )
    except Exception:
        pass

    db.commit()

    return {"message": "Decision saved", "od_request_id": od_request_id, "status": od.status}



@router.get("/absent/pending")
def get_pending_absence_requests(
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="Only CR allowed")

    cr_student = db.query(Student).filter(Student.id == cr["student_id"]).first()
    if not cr_student:
        raise HTTPException(status_code=404, detail="CR not found")

    pending = (
        db.query(AbsenceRequest)
        .filter(
            AbsenceRequest.status == "PENDING",
            AbsenceRequest.department == cr_student.department,
            AbsenceRequest.year == cr_student.year,
            AbsenceRequest.section == cr_student.section,
        )
        .order_by(AbsenceRequest.created_at.desc())
        .all()
    )

    return {
        "requests": [
            {
                "id": r.id,
                "roll": r.student_roll_number,
                "name": r.student_name,
                "category": r.category,
                "slots": r.slots,
                "date": r.request_date.isoformat(),
                "reason": r.reason,
                "proof_url": r.proof_url,
                "proof_type": r.proof_type,
                "status": r.status,
                "cr_remarks": r.cr_remarks,
            }
            for r in pending
        ]
    }


@router.post("/absent/{absence_request_id}/decision")
def decide_absence_request(
    absence_request_id: int,
    decision: str = Form(...),
    remarks: str | None = Form(None),
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="Only CR allowed")

    cr_student = db.query(Student).filter(Student.id == cr["student_id"]).first()
    if not cr_student:
        raise HTTPException(status_code=404, detail="CR not found")

    req = db.query(AbsenceRequest).filter(AbsenceRequest.id == absence_request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Absence request not found")

    if not (
        req.department == cr_student.department
        and req.year == cr_student.year
        and req.section == cr_student.section
    ):
        raise HTTPException(status_code=403, detail="Not in your section")

    decision_norm = decision.upper().strip()
    if decision_norm not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Invalid decision")

    req.status = decision_norm
    req.cr_remarks = remarks.strip() if remarks else None

    if decision_norm == "APPROVED":
        admin = (
            db.query(Admin)
            .filter(
                Admin.department == req.department,
                Admin.year == req.year,
                Admin.section == req.section,
            )
            .first()
        )
        if admin:
            _apply_absent_slot_attendance(db, req, admin)

        if req.category == "FULL_DAY":
            existing = db.query(DailyAttendance).filter(
                DailyAttendance.student_id == req.student_id,
                DailyAttendance.date == req.request_date,
            ).first()

            if existing:
                existing.status = "Absent"
                existing.source = "CR ABSENT"
                existing.marked_by = cr["student_id"]
            else:
                db.add(
                    DailyAttendance(
                        student_id=req.student_id,
                        date=req.request_date,
                        status="Absent",
                        source="CR ABSENT",
                        marked_by=cr["student_id"],
                    )
                )

    # notify the student for both APPROVED and REJECTED (user requested APPROVED + REJECTED)
    try:
        create_notification_for_student(
            db,
            student_id=req.student_id,
            message=f"Absence request {decision_norm.title()} ({req.request_date.isoformat()})",
            notification_type="ABSENCE_APPROVED" if decision_norm == "APPROVED" else "ABSENCE_REJECTED",
            meta={
                "absence_request_id": req.id,
                "date": req.request_date.isoformat(),
                "category": req.category,
                "slots": req.slots,
                "cr_remarks": req.cr_remarks,
            },
        )
    except Exception:
        pass

    db.commit()

    return {
        "message": "Decision saved",
        "absence_request_id": absence_request_id,
        "status": req.status,
    }



@router.get("/dashboard/summary")
def cr_dashboard_summary(
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    cr_student = db.query(Student).filter(
        Student.id == cr["student_id"]
    ).first()

    today = date.today()

    total_students = (
        db.query(Student)
        .filter(
            Student.year == cr_student.year,
            Student.department == cr_student.department,
            Student.section == cr_student.section,
        )
        .count()
    )

    marked = (
        db.query(DailyAttendance)
        .join(Student)
        .filter(
            DailyAttendance.date == today,
            Student.year == cr_student.year,
            Student.department == cr_student.department,
            Student.section == cr_student.section,
        )
        .count()
    )

    last_scan = (
        db.query(DailyAttendance.created_at)
        .join(Student)
        .filter(
            DailyAttendance.date == today,
            Student.year == cr_student.year,
            Student.department == cr_student.department,
            Student.section == cr_student.section,
        )
        .order_by(DailyAttendance.created_at.desc())
        .first()
    )

    last_scan_time = (
        to_ist(last_scan[0]).strftime("%I:%M %p") if last_scan else "—"
    )

    pending_od = (
        db.query(ODRequest)
        .filter(
            ODRequest.status == "PENDING",
            ODRequest.department == cr_student.department,
            ODRequest.year == cr_student.year,
            ODRequest.section == cr_student.section,
        )
        .count()
    )

    pending_absent = (
        db.query(AbsenceRequest)
        .filter(
            AbsenceRequest.status == "PENDING",
            AbsenceRequest.department == cr_student.department,
            AbsenceRequest.year == cr_student.year,
            AbsenceRequest.section == cr_student.section,
        )
        .count()
    )

    open_grievances = (
        db.query(GrievanceRequest)
        .filter(
            GrievanceRequest.department == cr_student.department,
            GrievanceRequest.year == cr_student.year,
            GrievanceRequest.section == cr_student.section,
            GrievanceRequest.status.in_(["OPEN", "UNDER_REVIEW"]),
        )
        .count()
    )

    return {
        "section": f"{cr_student.department} – {cr_student.year} {cr_student.section}",
        "total_students": total_students,
        "marked": marked,
        "pending_od": pending_od,
        "pending_absent": pending_absent,
        "open_grievances": open_grievances,
        "last_scan": last_scan_time,
    }


@router.get("/grievances")
def get_class_grievances(
    status: str | None = None,
    db: Session = Depends(get_db),
    cr=Depends(cr_required),
):
    query = db.query(GrievanceRequest).filter(
        GrievanceRequest.department == cr.department,
        GrievanceRequest.year == cr.year,
        GrievanceRequest.section == cr.section,
    )

    if status:
        normalized_status = status.strip().upper().replace(" ", "_")
        query = query.filter(GrievanceRequest.status == normalized_status)

    grievances = query.order_by(GrievanceRequest.created_at.desc()).all()

    return {
        "requests": [
            {
                "id": g.id,
                "roll_number": g.student_roll_number,
                "name": g.student_name,
                "grievance_type": g.grievance_type,
                "slot": g.slot,
                "request_date": str(g.request_date),
                "description": g.description,
                "proof_url": g.proof_url,
                "status": g.status.title().replace("_", " "),
                "review_remarks": g.review_remarks,
            }
            for g in grievances
        ]
    }


@router.post("/grievances/{grievance_id}/decision")
def review_grievance(
    grievance_id: int,
    decision_data: GrievanceDecisionSchema = Body(...),
    db: Session = Depends(get_db),
    cr=Depends(cr_required),
):
    raise HTTPException(
        status_code=403,
        detail="CRs can only view grievances. Only admins may update grievance status.",
    )


# ===================== PDF PRESENT =====================
@router.get("/attendance/daily/export/present/pdf")
def export_present_pdf(
    cr=Depends(student_required),
    db: Session = Depends(get_db),
):
    # 🔐 CR ONLY
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    today = date.today()

    # ✅ Fetch attendance with student join
    records = (
        db.query(DailyAttendance, Student)
        .join(Student, DailyAttendance.student_id == Student.id)
        .filter(
            DailyAttendance.date == today,
            Student.department == cr.department,
            Student.year == cr.year,
            Student.section == cr.section,
        )
        .order_by(DailyAttendance.created_at)
        .all()
    )

    # ===== PDF SETUP =====
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    # ===== HEADER =====
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, "DAILY ATTENDANCE REPORT")
    y -= 1 * cm

    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, f"Department : {cr['department']}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Year / Section : {cr['year']} {cr['section']}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Date : {today}")
    y -= 1 * cm

    # ===== TABLE HEADER =====
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, "Roll Number")
    c.drawString(7 * cm, y, "Name")
    c.drawString(14 * cm, y, "Time")
    y -= 0.6 * cm

    c.setFont("Helvetica", 10)

    # ===== DATA ROWS =====
    for attendance, student in records:
        if y < 2 * cm:
            c.showPage()
            y = height - 2 * cm

        c.drawString(2 * cm, y, student.roll_number)
        c.drawString(7 * cm, y, student.name)
        c.drawString(
            14 * cm,
            y,
            attendance.created_at.strftime("%I:%M %p")
            if attendance.created_at else "-"
        )
        y -= 0.4 * cm

    # ===== FOOTER =====
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        2 * cm,
        1.5 * cm,
        f"Report generated at {datetime.now().strftime('%d-%m-%Y %I:%M %p')}",
    )
    c.drawRightString(
        width - 2 * cm,
        1.5 * cm,
        "© 2026 MINDURA TECHNOLOGIES. All rights reserved."
    )

    c.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=present_{today}.pdf"
        },
    )



# ===================== PDF ABSENT =====================
@router.get("/attendance/daily/export/absent/pdf")
def export_absent_pdf(
    db: Session = Depends(get_db),
    cr=Depends(student_required),
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    today = date.today()
    cr_student = db.query(Student).filter(Student.id == cr["student_id"]).first()

    present_ids = (
        db.query(DailyAttendance.student_id)
        .filter(DailyAttendance.date == today)
        .subquery()
    )

    students = (
        db.query(Student)
        .filter(
            Student.department == cr_student.department,
            Student.year == cr_student.year,
            Student.section == cr_student.section,
            ~Student.id.in_(present_ids),
        )
        .order_by(Student.roll_number)
        .all()
    )

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = draw_header(c, width, height, "ABSENTEE REPORT", cr_student, today)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, "Roll Number")
    c.drawString(7 * cm, y, "Name")
    y -= 0.5 * cm
    c.setFont("Helvetica", 10)

    for s in students:
        if y < 3 * cm:
            c.showPage()
            y = draw_header(c, width, height, "ABSENTEE REPORT", cr_student, today)

        c.drawString(2 * cm, y, s.roll_number)
        c.drawString(7 * cm, y, s.name)
        y -= 0.4 * cm

    draw_footer(c, width)
    c.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=absent_{today}.pdf"},
    )