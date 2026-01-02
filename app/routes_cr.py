from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime
from zoneinfo import ZoneInfo
from io import BytesIO

from app.database import SessionLocal
from app.models import DailyAttendance, Student
from app.dependencies import student_required, cr_required
from app.schemas import DailyAttendanceScanSchema

from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# ==============================
# CONFIG
# ==============================
router = APIRouter(prefix="/cr", tags=["Class Representative"])
IST = ZoneInfo("Asia/Kolkata")

# ==============================
# DB DEPENDENCY
# ==============================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==============================
# MARK DAILY ATTENDANCE (SCAN)
# ==============================
@router.post("/attendance/daily/scan")
def mark_daily_attendance(
    data: DailyAttendanceScanSchema,
    db: Session = Depends(get_db),
    cr=Depends(student_required)
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    student = (
        db.query(Student)
        .filter(Student.roll_number == data.student_roll)
        .first()
    )

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    existing = (
        db.query(DailyAttendance)
        .filter(
            DailyAttendance.student_id == student.id,
            DailyAttendance.date == date.today()
        )
        .first()
    )

    if existing:
        return {
            "message": "Attendance already marked",
            "status": existing.status
        }

    attendance = DailyAttendance(
        student_id=student.id,
        date=date.today(),
        status="Present",
        source="CR_SCAN",
        marked_by=cr["student_id"]
    )

    db.add(attendance)
    db.commit()

    return {
        "message": "Attendance marked successfully",
        "roll_number": student.roll_number
    }

# ==============================
# GET TODAY PRESENT (CR VIEW)
# ==============================
@router.get("/attendance/daily/today")
def get_today_present(
    db: Session = Depends(get_db),
    cr=Depends(student_required)
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    today = date.today()

    cr_student = (
        db.query(Student)
        .filter(Student.id == cr["student_id"])
        .first()
    )

    records = (
        db.query(DailyAttendance, Student)
        .join(Student, DailyAttendance.student_id == Student.id)
        .filter(
            DailyAttendance.date == today,
            Student.department == cr_student.department,
            Student.year == cr_student.year,
            Student.section == cr_student.section
        )
        .order_by(DailyAttendance.created_at)
        .all()
    )

    return {
        "date": str(today),
        "class": f"{cr_student.year} {cr_student.department} {cr_student.section}",
        "scanned": [
            {
                "roll_number": s.roll_number,
                "name": s.name,
                # ✅ IST FIX HERE
                "time": a.created_at.astimezone(IST).strftime("%I:%M %p"),
            }
            for a, s in records
        ],
    }

# ==============================
# GET TODAY ABSENT
# ==============================
@router.get("/attendance/daily/absent")
def get_today_absent(
    db: Session = Depends(get_db),
    cr=Depends(student_required)
):
    if not cr["is_cr"]:
        raise HTTPException(status_code=403, detail="CR only")

    today = date.today()

    cr_student = (
        db.query(Student)
        .filter(Student.id == cr["student_id"])
        .first()
    )

    present_ids = (
        db.query(DailyAttendance.student_id)
        .join(Student, DailyAttendance.student_id == Student.id)
        .filter(
            DailyAttendance.date == today,
            Student.department == cr_student.department,
            Student.year == cr_student.year,
            Student.section == cr_student.section
        )
        .subquery()
    )

    absentees = (
        db.query(Student)
        .filter(
            Student.department == cr_student.department,
            Student.year == cr_student.year,
            Student.section == cr_student.section,
            ~Student.id.in_(present_ids)
        )
        .order_by(Student.roll_number)
        .all()
    )

    return {
        "date": str(today),
        "class": f"{cr_student.year} {cr_student.department} {cr_student.section}",
        "absent": [
            {
                "roll_number": s.roll_number,
                "name": s.name,
            }
            for s in absentees
        ],
    }

# ==============================
# EXPORT PRESENT PDF
# ==============================
@router.get("/attendance/daily/export/present/pdf")
def export_present_pdf(
    cr=Depends(cr_required),
    db: Session = Depends(get_db),
):
    today = date.today()

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

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    # HEADER
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, "DAILY ATTENDANCE REPORT")
    y -= 1 * cm

    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, f"Department : {cr.department}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Year / Section : {cr.year} {cr.section}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Date : {today}")
    y -= 1 * cm

    # TABLE HEADER
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, "Roll Number")
    c.drawString(7 * cm, y, "Name")
    c.drawString(14 * cm, y, "Time")
    y -= 0.5 * cm

    c.setFont("Helvetica", 10)

    for attendance, student in records:
        if y < 2 * cm:
            c.showPage()
            y = height - 2 * cm

        c.drawString(2 * cm, y, student.roll_number)
        c.drawString(7 * cm, y, student.name)
        # ✅ IST FIX
        c.drawString(
            14 * cm,
            y,
            attendance.created_at.astimezone(IST).strftime("%I:%M %p")
        )
        y -= 0.4 * cm

    # FOOTER (IST FIX)
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(
        width / 2,
        2 * cm,
        f"Report generated on : {datetime.now(IST).strftime('%d-%m-%Y %I:%M %p')}",
    )
    c.drawCentredString(
        width / 2,
        1.4 * cm,
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

# ==============================
# EXPORT ABSENT PDF
# ==============================
@router.get("/attendance/daily/export/absent/pdf")
def export_absent_pdf(
    cr=Depends(cr_required),
    db: Session = Depends(get_db),
):
    today = date.today()

    present_ids = (
        db.query(DailyAttendance.student_id)
        .filter(DailyAttendance.date == today)
        .subquery()
    )

    students = (
        db.query(Student)
        .filter(
            Student.department == cr.department,
            Student.year == cr.year,
            Student.section == cr.section,
            ~Student.id.in_(present_ids),
        )
        .order_by(Student.roll_number)
        .all()
    )

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, "ABSENTEE REPORT")
    y -= 1 * cm

    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, f"Department : {cr.department}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Year / Section : {cr.year} {cr.section}")
    y -= 0.5 * cm
    c.drawString(2 * cm, y, f"Date : {today}")
    y -= 1 * cm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, "Roll Number")
    c.drawString(7 * cm, y, "Name")
    y -= 0.5 * cm

    c.setFont("Helvetica", 10)

    for s in students:
        if y < 2 * cm:
            c.showPage()
            y = height - 2 * cm

        c.drawString(2 * cm, y, s.roll_number)
        c.drawString(7 * cm, y, s.name)
        y -= 0.4 * cm

    # FOOTER (IST FIX)
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(
        width / 2,
        2 * cm,
        f"Report generated on : {datetime.now(IST).strftime('%d-%m-%Y %I:%M %p')}",
    )
    c.drawCentredString(
        width / 2,
        1.4 * cm,
        "© 2026 MINDURA TECHNOLOGIES. All rights reserved."
    )

    c.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=absent_{today}.pdf"
        },
    )

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

