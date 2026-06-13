from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text, func, distinct
import secrets
from datetime import date

from app.database import SessionLocal
from app.models import (
    Student,
    QRSession,
    GrievanceRequest,
    DailyAttendance,
    SemesterSettings,
    Slot,
    Attendance,
    Timetable,
    Subject,
    TimeSlot,
    CRAssignment,
    HolidayDeclaration,
)


from app.schemas import (
    StudentRegisterSchema,
    GrievanceDecisionSchema,
    SemesterCreateSchema,
    SlotCreateSchema,
    SubjectCreateSchema,
    TimeSlotCreateSchema,
    WeeklyTimetableUpsertSchema,
    CRAssignmentCurrentUpsertSchema,
    CRAssignmentBackupUpsertSchema,
    CRAssignmentRemoveSchema,
    HolidayDeclareSchema,
)


from app.dependencies import admin_required
from app.utils.qr import generate_dynamic_qr, cleanup_old_qr
from app.semester_year_utils import advance_year_value


router = APIRouter(prefix="/admin", tags=["Admin"])

# --- Admin UI placeholders ---
# These routes exist ONLY so that reverse proxies/hosting that forward /admin/* to the backend
# won't return a 404 on hard-refresh. Actual UI is rendered by the React app.

from datetime import date as _date

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/me")
def admin_me(admin=Depends(admin_required)):
    return admin


# -------------------- CR Assignment (Admin) --------------------
@router.get("/cr-control")
def admin_cr_control_data(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    # debug helper: admin['admin_id'] exists when token is valid

    assignment = (
        db.query(CRAssignment)
        .filter(
            CRAssignment.department == admin["department"],
            CRAssignment.year == admin["year"],
            CRAssignment.section == admin["section"],
        )
        .first()
    )

    current_cr = None
    backup_cr = None

    if assignment:
        if assignment.current_cr_student_id is not None:
            current_cr = (
                db.query(Student)
                .filter(Student.id == assignment.current_cr_student_id)
                .first()
            )
        if assignment.backup_cr_student_id is not None:
            backup_cr = (
                db.query(Student)
                .filter(Student.id == assignment.backup_cr_student_id)
                .first()
            )

    today = _date.today()

    def active(from_d, to_d):
        if from_d is not None and from_d > today:
            return False
        if to_d is not None and to_d < today:
            return False
        return True

    current_active = False
    if assignment and assignment.current_cr_student_id is not None:
        current_active = active(assignment.valid_from, assignment.valid_to)

    return {
        "current": (
            {
                "student_id": current_cr.id,
                "roll": current_cr.roll_number,
                "name": current_cr.name,
                "validFrom": assignment.valid_from.isoformat() if assignment and assignment.valid_from else None,
                "validTo": assignment.valid_to.isoformat() if assignment and assignment.valid_to else None,
                "active": current_active,
            }
            if current_cr and assignment
            else None
        ),
        "backup": (
            {
                "student_id": backup_cr.id,
                "roll": backup_cr.roll_number,
                "name": backup_cr.name,
            }
            if backup_cr and assignment and assignment.backup_cr_student_id is not None
            else None
        ),
    }


@router.post("/cr-assignment/current")
def admin_upsert_cr_current(
    data: CRAssignmentCurrentUpsertSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    assignment = (
        db.query(CRAssignment)
        .filter(
            CRAssignment.department == admin["department"],
            CRAssignment.year == admin["year"],
            CRAssignment.section == admin["section"],
        )
        .first()
    )

    if not data.current_cr_student_id:
        raise HTTPException(status_code=400, detail="current_cr_student_id is required")
    if not data.valid_from or not data.valid_to:
        raise HTTPException(status_code=400, detail="valid_from and valid_to are required")

    cr_student = (
        db.query(Student)
        .filter(
            Student.id == data.current_cr_student_id,
            Student.department == admin["department"],
            Student.year == admin["year"],
            Student.section == admin["section"],
        )
        .first()
    )
    if not cr_student:
        raise HTTPException(status_code=400, detail="CR student not in your section")

    if not assignment:
        assignment = CRAssignment(
            department=admin["department"],
            year=admin["year"],
            section=admin["section"],
        )
        db.add(assignment)

    assignment.current_cr_student_id = data.current_cr_student_id
    assignment.valid_from = data.valid_from
    assignment.valid_to = data.valid_to

    db.commit()
    return {"message": "Current CR updated"}


@router.post("/cr-assignment/backup")
def admin_upsert_cr_backup(
    data: CRAssignmentBackupUpsertSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    assignment = (
        db.query(CRAssignment)
        .filter(
            CRAssignment.department == admin["department"],
            CRAssignment.year == admin["year"],
            CRAssignment.section == admin["section"],
        )
        .first()
    )

    if not data.backup_cr_student_id:
        raise HTTPException(status_code=400, detail="backup_cr_student_id is required")

    backup_student = (
        db.query(Student)
        .filter(
            Student.id == data.backup_cr_student_id,
            Student.department == admin["department"],
            Student.year == admin["year"],
            Student.section == admin["section"],
        )
        .first()
    )
    if not backup_student:
        raise HTTPException(status_code=400, detail="Backup CR student not in your section")

    if not assignment:
        assignment = CRAssignment(
            department=admin["department"],
            year=admin["year"],
            section=admin["section"],
        )
        db.add(assignment)

    assignment.backup_cr_student_id = data.backup_cr_student_id
    db.commit()
    return {"message": "Backup CR updated"}


@router.post("/cr-assignment/remove")
def admin_remove_cr_assignment(
    _data: CRAssignmentRemoveSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    assignment = (
        db.query(CRAssignment)
        .filter(
            CRAssignment.department == admin["department"],
            CRAssignment.year == admin["year"],
            CRAssignment.section == admin["section"],
        )
        .first()
    )

    if assignment:
        assignment.current_cr_student_id = None
        assignment.backup_cr_student_id = None
        assignment.valid_from = None
        assignment.valid_to = None
        db.commit()

    return {"message": "CR assignment removed"}


# --------------------------------------------------
# ADMIN: STUDENTS (register + list for CR control)
# --------------------------------------------------
@router.post("/students")
def register_student(
    data: StudentRegisterSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    if db.query(Student).filter(Student.roll_number == data.roll_number).first():
        raise HTTPException(status_code=400, detail="Student already exists")

    student = Student(**data.dict())
    db.add(student)
    db.commit()
    db.refresh(student)

    return {
        "message": "Student registered successfully",
        "roll_number": student.roll_number,
    }


@router.get("/students")
def list_students_for_admin_cr(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    # Normalize whitespace to avoid empty lists due to trailing spaces / formatting differences.
    rows = (
        db.query(Student)
        .filter(
            func.upper(func.trim(Student.department)) == func.upper(func.trim(admin["department"])),
            func.upper(func.trim(Student.year)) == func.upper(func.trim(admin["year"])),
            func.upper(func.trim(Student.section)) == func.upper(func.trim(admin["section"])),
        )
        .order_by(Student.roll_number.asc())
        .all()
    )
    return {
        "students": [
            {
                "roll_number": s.roll_number,
                "roll": s.roll_number,
                "name": s.name,
                "id": s.id,
            }
            for s in rows
        ]
    }



# --------------------------------------------------
# ADMIN: SEMESTER
# --------------------------------------------------
@router.post("/semester")
def set_semester(
    data: SemesterCreateSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    db.query(SemesterSettings).filter(
        SemesterSettings.admin_id == admin["admin_id"]
    ).delete()

    semester = SemesterSettings(
        admin_id=admin["admin_id"],
        start_date=data.start_date,
        end_date=data.end_date,
    )

    db.add(semester)
    db.commit()

    return {"message": "Semester duration set successfully"}


@router.post("/semester/reset")
def reset_semester(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):



    inspector = inspect(db.bind)

    tables_to_reset = [
        "daily_attendance",
        "attendance",
        "timetable",
        "subjects",
        "qr_sessions",
    ]

    for table in tables_to_reset:
        if inspector.has_table(table):
            # SQLite does not support TRUNCATE. Use DELETE.
            # Use raw SQL so it works consistently with SQLAlchemy models.
            db.execute(text(f"DELETE FROM {table}"))




    db.commit()

    # Optional: keep backward compatibility for frontend calls
    # (no-op default; actual year advance is handled by /semester/reset/advance-year)

    return {"message": "Semester reset successful. Students retained."}


@router.post("/semester/reset/advance-year")
def advance_student_years_after_reset(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    # Advance student.year by +1 for the admin's department/year/section scope.
    # This is best-effort and only affects students in the current admin scope.

    # Map roman years I->II->III->IV (IV stays IV)
    today = date.today()  # kept for future extensions

    # Update all students in current admin scope
    students = (
        db.query(Student)
        .filter(
            Student.department == admin["department"],
            Student.year == admin["year"],
            Student.section == admin["section"],
        )
        .all()
    )

    for s in students:
        s.year = advance_year_value(s.year)

    db.commit()

    return {"message": "Student years advanced successfully", "updated": len(students)}



# --------------------------------------------------
# ADMIN: SLOTS
# --------------------------------------------------
@router.post("/slots")
def create_slot(
    data: SlotCreateSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    if db.query(Slot).filter(Slot.slot_number == data.slot_number).first():
        raise HTTPException(status_code=400, detail="Slot already exists")

    slot = Slot(
        slot_number=data.slot_number,
        start_time=data.start_time,
        end_time=data.end_time,
    )

    db.add(slot)
    db.commit()

    return {"message": f"Slot {data.slot_number} created successfully"}


# --------------------------------------------------
# ADMIN: QR GENERATION
# --------------------------------------------------
@router.post("/qr/generate")
def generate_qr_for_slot(
    subject_code: str,
    slot_name: str,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    cleanup_old_qr(db)

    existing = db.query(QRSession).filter(
        QRSession.admin_id == admin["admin_id"],
        QRSession.subject_code == subject_code,
        QRSession.slot_name == slot_name,
        QRSession.date == date.today(),
    ).first()

    if not existing:
        secret = secrets.token_hex(16)
        qr_session = QRSession(
            admin_id=admin["admin_id"],
            subject_code=subject_code,
            slot_name=slot_name,
            secret=secret,
        )
        db.add(qr_session)
        db.commit()
        db.refresh(qr_session)
    else:
        qr_session = existing

    qr_value = generate_dynamic_qr(qr_session.secret)

    return {
        "slot": slot_name,
        "subject": subject_code,
        "qr": qr_value,
        "valid_for_seconds": 3,
    }


# -------------------- Admin Dashboard & other existing endpoints --------------------
@router.get("/dashboard/stats")
def admin_dashboard_stats(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    today = date.today()

    total_students = db.query(Student).filter(
        Student.department == admin["department"],
        Student.year == admin["year"],
        Student.section == admin["section"],
    ).count()

    sections = db.query(Student.department, Student.year, Student.section).distinct().count()

    present_today = db.query(DailyAttendance).filter(
        DailyAttendance.date == today,
        DailyAttendance.status == "Present",
    ).count()

    total_marked_today = db.query(DailyAttendance).filter(DailyAttendance.date == today).count()

    present_percent = (
        round((present_today / total_marked_today) * 100)
        if total_marked_today > 0
        else 0
    )

    pending_od = db.query(DailyAttendance).filter(DailyAttendance.status == "OD").count()

    semester = db.query(SemesterSettings).filter(SemesterSettings.admin_id == admin["admin_id"]).first()

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
        "days_left": days_left,
    }


@router.get("/grievances")
def admin_grievances(
    status: str | None = None,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    query = db.query(GrievanceRequest).filter(
        GrievanceRequest.department == admin["department"],
        GrievanceRequest.year == admin["year"],
        GrievanceRequest.section == admin["section"],
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
def admin_review_grievance(
    grievance_id: int,
    decision_data: GrievanceDecisionSchema = Body(...),
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    normalized_decision = decision_data.decision.strip().upper().replace(" ", "_")
    remarks = decision_data.remarks

    if normalized_decision not in ["OPEN", "UNDER_REVIEW", "RESOLVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Invalid grievance decision")

    grievance = db.query(GrievanceRequest).filter(
        GrievanceRequest.id == grievance_id,
        GrievanceRequest.department == admin["department"],
        GrievanceRequest.year == admin["year"],
        GrievanceRequest.section == admin["section"],
    ).first()

    if not grievance:
        raise HTTPException(status_code=404, detail="Grievance not found")

    grievance.status = normalized_decision
    grievance.review_remarks = remarks.strip() if remarks and remarks.strip() else grievance.review_remarks
    db.commit()

    return {
        "message": "Grievance updated successfully",
        "status": grievance.status.title().replace("_", " "),
    }


@router.get("/attendance/daily")
def get_daily_attendance(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    today = date.today()

    students = db.query(Student).filter(
        Student.department == admin["department"],
        Student.year == admin["year"],
        Student.section == admin["section"],
    ).all()

    attendance_map = {
        a.student_id: a
        for a in db.query(DailyAttendance).filter(DailyAttendance.date == today).all()
    }

    return [
        {
            "roll": s.roll_number,
            "name": s.name,
            "status": attendance_map[s.id].status if s.id in attendance_map else "Absent",
            "source": attendance_map[s.id].source if s.id in attendance_map else "Not Marked",
        }
        for s in students
    ]


@router.get("/attendance/slots")
def get_slot_attendance(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    today = date.today()

    data = db.query(
        Subject.name.label("subject"),
        TimeSlot.slot_name.label("slot"),
        func.count(Attendance.id).label("present"),
    ).join(
        Timetable, Timetable.subject_id == Subject.id
    ).join(
        TimeSlot, Timetable.slot_id == TimeSlot.id
    ).outerjoin(
        Attendance,
        (Attendance.slot == TimeSlot.id)
        & (Attendance.date == today)
        & (Attendance.status == "PRESENT"),
    ).filter(
        Timetable.admin_id == admin["admin_id"]
    ).group_by(
        Subject.name, TimeSlot.slot_name
    ).all()

    total_students = db.query(Student).filter(
        Student.department == admin["department"],
        Student.year == admin["year"],
        Student.section == admin["section"],
    ).count()

    return [
        {"subject": row.subject, "slot": row.slot, "present": row.present, "total": total_students}
        for row in data
    ]


@router.get("/attendance/report")
def attendance_report(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    students = db.query(Student).filter(
        Student.department == admin["department"],
        Student.year == admin["year"],
        Student.section == admin["section"],
    ).all()

    working_days = db.query(func.count(distinct(DailyAttendance.date))).scalar() or 0

    report = []
    for s in students:
        present_days = db.query(DailyAttendance).filter(
            DailyAttendance.student_id == s.id,
            DailyAttendance.status == "PRESENT",
        ).count()

        percentage = round((present_days / working_days) * 100, 2) if working_days > 0 else 0

        report.append(
            {
                "roll": s.roll_number,
                "name": s.name,
                "working_days": working_days,
                "present_days": present_days,
                "percentage": percentage,
            }
        )

    return report


# -------------------- Timetable Management (keep as-is) --------------------
@router.post("/subjects")
def admin_create_subject(
    data: SubjectCreateSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    existing = db.query(Subject).filter(
        Subject.admin_id == admin["admin_id"],
        Subject.code == data.code.strip(),
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Subject already exists")

    subj = Subject(
        name=data.name.strip(),
        code=data.code.strip(),
        admin_id=admin["admin_id"],
    )

    db.add(subj)
    db.commit()
    db.refresh(subj)

    return {"message": "Subject created successfully", "subject": {"id": subj.id, "code": subj.code, "name": subj.name}}


@router.get("/subjects")
def admin_list_subjects(db: Session = Depends(get_db), admin=Depends(admin_required)):
    rows = (
        db.query(Subject)
        .filter(Subject.admin_id == admin["admin_id"])
        .order_by(Subject.code.asc())
        .all()
    )
    return {"subjects": [{"id": r.id, "code": r.code, "name": r.name} for r in rows]}


@router.post("/time-slots")
def admin_create_time_slot(
    data: TimeSlotCreateSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    existing = db.query(TimeSlot).filter(
        TimeSlot.admin_id == admin["admin_id"],
        TimeSlot.slot_name == data.slot_name,
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Slot already exists")

    ts = TimeSlot(
        slot_name=data.slot_name.strip(),
        start_time=data.start_time,
        end_time=data.end_time,
        admin_id=admin["admin_id"],
    )

    db.add(ts)
    db.commit()
    db.refresh(ts)

    return {"message": "Slot created successfully", "slot": {"id": ts.id, "slot_name": ts.slot_name}}


@router.get("/time-slots")
def admin_list_time_slots(db: Session = Depends(get_db), admin=Depends(admin_required)):
    rows = (
        db.query(TimeSlot)
        .filter(TimeSlot.admin_id == admin["admin_id"])
        .order_by(TimeSlot.slot_name.asc())
        .all()
    )
    return {
        "time_slots": [
            {
                "id": r.id,
                "slot_name": r.slot_name,
                "start_time": r.start_time.strftime("%H:%M"),
                "end_time": r.end_time.strftime("%H:%M"),
            }
            for r in rows
        ]
    }


@router.post("/weekly-timetable")
def admin_upsert_weekly_timetable(
    data: WeeklyTimetableUpsertSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    for cell in data.cells:
        if cell.subject_id is None:
            db.query(Timetable).filter(
                Timetable.admin_id == admin["admin_id"],
                Timetable.day == cell.day,
                Timetable.slot_id == cell.slot_id,
            ).delete(synchronize_session=False)
            continue

        subj = db.query(Subject).filter(
            Subject.id == cell.subject_id,
            Subject.admin_id == admin["admin_id"],
        ).first()
        if not subj:
            raise HTTPException(status_code=400, detail="Invalid subject")

        existing = db.query(Timetable).filter(
            Timetable.admin_id == admin["admin_id"],
            Timetable.day == cell.day,
            Timetable.slot_id == cell.slot_id,
        ).first()

        if existing:
            existing.subject_id = cell.subject_id
        else:
            db.add(
                Timetable(
                    day=cell.day,
                    slot_id=cell.slot_id,
                    subject_id=cell.subject_id,
                    admin_id=admin["admin_id"],
                )
            )

    db.commit()
    return {"message": "Weekly timetable saved"}


@router.get("/weekly-timetable")
def admin_get_weekly_timetable(db: Session = Depends(get_db), admin=Depends(admin_required)):
    rows = db.query(Timetable).filter(Timetable.admin_id == admin["admin_id"]).all()
    out = []
    for t in rows:
        out.append(
            {
                "day": t.day,
                "slot_id": t.slot_id,
                "subject_id": t.subject_id,
                "subject_code": t.subject.code if getattr(t, "subject", None) else None,
                "subject_name": t.subject.name if getattr(t, "subject", None) else None,
            }
        )
    return {"timetable": out}


# ===================== HOLIDAY DECLARATION (Admin) =====================
@router.post("/attendance/holiday/declare")
def declare_holiday(
    data: HolidayDeclareSchema,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    # Save as section-scoped announcement; students will interpret from today up to holiday_date.
    hd = HolidayDeclaration(
        department=admin["department"],
        year=admin["year"],
        section=admin["section"],
        holiday_date=data.holiday_date,
        reason=(data.reason.strip() if data.reason else None),
    )

    db.add(hd)
    db.commit()
    db.refresh(hd)

    return {
        "message": "Holiday declared successfully",
        "holiday_date": hd.holiday_date.isoformat(),
        "reason": hd.reason,
    }


