# presenza-backend/app/routes_cr.py

from fastapi import APIRouter, Depends, HTTPException
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
from app.models import DailyAttendance, Student
from app.dependencies import student_required
from app.schemas import DailyAttendanceScanSchema
from app.schemas import CRManualAttendanceBulkSchema


router = APIRouter(prefix="/cr", tags=["Class Representative"])

IST = pytz.timezone("Asia/Kolkata")


# ===================== DB =====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        status="Present",
        source="CR_SCAN",
        marked_by=cr["student_id"],
    )

    db.add(attendance)
    db.commit()

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

    # Fetch CR student record
    cr_student = db.query(Student).filter(
        Student.id == cr["student_id"]
    ).first()

    if not cr_student:
        raise HTTPException(status_code=404, detail="CR student not found")

    # Fetch all students of CR class
    students = db.query(Student).filter(
        Student.department == cr_student.department,
        Student.year == cr_student.year,
        Student.section == cr_student.section,
    ).all()

    if not students:
        raise HTTPException(status_code=404, detail="No students found")

    present_set = set(data.present_roll_numbers)

    for student in students:
        status = "PRESENT" if student.roll_number in present_set else "ABSENT"

        existing = db.query(DailyAttendance).filter(
            DailyAttendance.student_id == student.id,
            DailyAttendance.date == today,
        ).first()

        if existing:
            existing.status = status
            existing.source = "CR_MANUAL"
        else:
            attendance = DailyAttendance(
                student_id=student.id,
                date=today,
                status=status,
                source="CR_MANUAL",
            )
            db.add(attendance)

    db.commit()

    return {
        "message": "Manual attendance submitted successfully",
        "date": today.strftime("%d-%m-%Y"),
        "present_count": len(data.present_roll_numbers),
        "total_students": len(students),
    }
# ===================== STUDENT LIST FOR MANUAL ATTENDANCE =====================

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

    return {
        "section": f"{cr_student.department} – {cr_student.year} {cr_student.section}",
        "total_students": total_students,
        "marked": marked,
        "pending_od": 0,
        "open_grievances": 0,
        "last_scan": last_scan_time,
    }

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