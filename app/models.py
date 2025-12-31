#prazenza-backend/app/models.py
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey,Float,Time
from sqlalchemy.sql import func
from .database import Base
from sqlalchemy.orm import relationship
from datetime import datetime,date






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

    student_id = Column(
        Integer,
        ForeignKey("students.id"),
        nullable=False
    )

    date = Column(Date, nullable=False)

    status = Column(
        String,
        default="Present"
    )  # Present | Absent | OD

    source = Column(
        String,
        nullable=False
    )  # CR_SCAN | QR_BACKUP | SELF

    marked_by = Column(
        Integer,
        nullable=True
    )  # CR student_id

    created_at = Column(
        DateTime,
        server_default=func.now()
    )



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

    created_at = Column(Date, default=datetime.utcnow)


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


class Timetable(Base):
    __tablename__ = "timetable"

    id = Column(Integer, primary_key=True)
    day = Column(String, nullable=False)  # Monday, Tuesday
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
    slot_name = Column(String)              # e.g. Slot-1
    date = Column(Date, default=func.current_date())

    secret = Column(String, nullable=False) # used to generate dynamic QR
    created_at = Column(Time, server_default=func.current_time())


class QRScanAttendance(Base):
    __tablename__ = "qr_scan_attendance"

    id = Column(Integer, primary_key=True, index=True)
    student_roll = Column(String, index=True)
    subject_code = Column(String)
    slot_name = Column(String)
    date = Column(Date, default=date.today)
    scanned_at = Column(DateTime, default=datetime.utcnow)
