#prazenza-backend/app/models.py
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Float, Time


from sqlalchemy.sql import func
from .database import Base
from sqlalchemy.orm import relationship
from datetime import datetime, date


class ODRequest(Base):
    __tablename__ = "od_requests"

    # Notes:
    # - category: FULL_DAY | SLOT
    # - slots: comma-separated slot names (e.g. "Slot 1,Slot 3") for SLOT-wise requests

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    student_roll_number = Column(String, nullable=False, index=True)
    student_name = Column(String, nullable=False)

    department = Column(String, nullable=False, index=True)
    year = Column(String, nullable=False, index=True)
    section = Column(String, nullable=False, index=True)

    request_date = Column(Date, nullable=False, default=date.today)

    # FULL_DAY / SLOT
    category = Column(String, nullable=False)  # FULL_DAY | SLOT

    # For SLOT-wise requests: comma-separated slots like "Slot 1,Slot 2"
    # (kept simple to avoid JSON/extra tables)
    slots = Column(String)  # nullable; used only when category == SLOT

    reason = Column(String, nullable=False)

    proof_url = Column(String, nullable=False)  # points to stored file under /static
    proof_type = Column(String, nullable=True)

    status = Column(String, default="PENDING")  # PENDING | APPROVED | REJECTED
    cr_remarks = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class AbsenceRequest(Base):
    __tablename__ = "absence_requests"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    student_roll_number = Column(String, nullable=False, index=True)
    student_name = Column(String, nullable=False)

    department = Column(String, nullable=False, index=True)
    year = Column(String, nullable=False, index=True)
    section = Column(String, nullable=False, index=True)

    request_date = Column(Date, nullable=False, default=date.today)

    category = Column(String, nullable=False)  # FULL_DAY | SLOT
    slots = Column(String)  # comma-separated slot names when category == SLOT

    reason = Column(String, nullable=False)

    proof_url = Column(String, nullable=True)
    proof_type = Column(String, nullable=True)

    status = Column(String, default="PENDING")  # PENDING | APPROVED | REJECTED
    cr_remarks = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class GrievanceRequest(Base):
    __tablename__ = "grievance_requests"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    student_roll_number = Column(String, nullable=False, index=True)
    student_name = Column(String, nullable=False)

    department = Column(String, nullable=False, index=True)
    year = Column(String, nullable=False, index=True)
    section = Column(String, nullable=False, index=True)

    request_date = Column(Date, nullable=False, default=date.today)
    grievance_type = Column(String, nullable=False)
    slot = Column(String, nullable=True)
    description = Column(String, nullable=False)

    proof_url = Column(String, nullable=True)
    proof_type = Column(String, nullable=True)

    status = Column(String, default="OPEN")  # OPEN | UNDER_REVIEW | RESOLVED | REJECTED
    review_remarks = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    roll_number = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    department = Column(String, nullable=False)
    year = Column(String, nullable=False)
    section = Column(String, nullable=False)
    mobile = Column(String, nullable=False)
    is_cr = Column(Boolean, default=False)


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(String, unique=True, nullable=False)

    department = Column(String, nullable=False)
    year = Column(String, nullable=False)
    section = Column(String, nullable=False)

    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class DailyAttendance(Base):
    __tablename__ = "daily_attendance"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    date = Column(Date, nullable=False)

    status = Column(String, default="Present")  # Present | Absent | OD

    source = Column(String, nullable=False)  # CR_SCAN | QR_BACKUP | SELF

    marked_by = Column(Integer, nullable=True)  # CR student_id

    created_at = Column(DateTime, server_default=func.now())


class AttendanceQR(Base):
    __tablename__ = "attendance_qr"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    slot = Column(Integer, nullable=False)
    subject = Column(String, nullable=False)
    qr_token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    date = Column(Date, nullable=False)
    slot = Column(Integer, nullable=False)
    status = Column(String, default="PRESENT")  # PRESENT / ABSENT / OD
    latitude = Column(Float)
    longitude = Column(Float)
    marked_at = Column(DateTime, server_default=func.now())


class SemesterSettings(Base):
    __tablename__ = "semester_settings"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(String, ForeignKey("admins.admin_id"), nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class Slot(Base):
    __tablename__ = "slots"

    id = Column(Integer, primary_key=True, index=True)
    slot_number = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    code = Column(String, nullable=False)
    admin_id = Column(String, nullable=False)


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True)
    slot_name = Column(String, nullable=False)  # Slot 1, Slot 2
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    admin_id = Column(String, nullable=False)


class HolidayDeclaration(Base):
    __tablename__ = "holiday_declarations"

    id = Column(Integer, primary_key=True, index=True)

    department = Column(String, nullable=False, index=True)
    year = Column(String, nullable=False, index=True)
    section = Column(String, nullable=False, index=True)

    holiday_date = Column(Date, nullable=False, index=True)

    # optional reason
    reason = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class Timetable(Base):
    __tablename__ = "timetable"


    id = Column(Integer, primary_key=True)
    day = Column(String, nullable=False)  # Monday..Friday
    slot_id = Column(Integer, ForeignKey("time_slots.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    admin_id = Column(String, nullable=False)

    slot = relationship("TimeSlot")
    subject = relationship("Subject")


class QRSession(Base):
    __tablename__ = "qr_sessions"

    id = Column(Integer, primary_key=True, index=True)

    admin_id = Column(String, index=True)  # ADMIN_CSE_I_B
    subject_code = Column(String, index=True)
    slot_name = Column(String)  # e.g. Slot-1
    date = Column(Date, default=func.current_date())

    secret = Column(String, nullable=False)  # used to generate dynamic QR
    created_at = Column(Time, server_default=func.current_time())


class QRScanAttendance(Base):
    __tablename__ = "qr_scan_attendance"

    id = Column(Integer, primary_key=True, index=True)
    student_roll = Column(String, index=True)
    subject_code = Column(String)
    slot_name = Column(String)
    date = Column(Date, default=date.today)
    scanned_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)

    # Exactly one of (recipient_student_id, recipient_admin_id) is set.
    recipient_student_id = Column(Integer, ForeignKey("students.id"), nullable=True, index=True)
    recipient_admin_id = Column(String, ForeignKey("admins.admin_id"), nullable=True, index=True)

    # "admin" | "student"
    recipient_role = Column(String, nullable=False, index=True)

    notification_type = Column(String, nullable=False, index=True)  # e.g. GRIEVANCE_SUBMITTED, OD_APPROVED, ATTENDANCE_MARKED
    message = Column(String, nullable=False)

    # simple JSON-like payload stored as string (for now)
    meta = Column(String, nullable=True)

    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, server_default=func.now())


class CRAssignment(Base):
    """Persist current + backup CR assignments with validity window."""



    __tablename__ = "cr_assignments"

    id = Column(Integer, primary_key=True, index=True)

    department = Column(String, nullable=False, index=True)
    year = Column(String, nullable=False, index=True)
    section = Column(String, nullable=False, index=True)

    current_cr_student_id = Column(Integer, ForeignKey("students.id"), nullable=True)
    backup_cr_student_id = Column(Integer, ForeignKey("students.id"), nullable=True)

    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

