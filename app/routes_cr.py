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