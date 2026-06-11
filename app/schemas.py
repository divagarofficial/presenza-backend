#prazenza-backend/app/schemas.py
from pydantic import BaseModel
from enum import Enum
from pydantic import BaseModel
from datetime import date, time
from typing import List, Optional





class DepartmentEnum(str, Enum):
    CSE = "BE COMPUTER SCIENCE AND ENGINEERING"
    AI_DS = "BTECH ARTIFICIAL INTELLIGENCE AND DATA SCIENCE"
    AIML = "BE COMPUTER SCIENCE AND ENGINEERING (AI&ML)"
    ECE = "BE ELECTRONICS AND COMMUNICATION ENGINEERING"
    VLSI = "BE ECE (VLSI)"
    CCE = "BE COMPUTER AND COMMUNICATION ENGINEERING"
    CSBS = "BTECH COMPUTER SCIENCE AND BUSINESS SYSTEMS"
    BIOTECH = "BTECH BIOTECHNOLOGY"


class YearEnum(str, Enum):
    I = "I"
    II = "II"
    III = "III"
    IV = "IV"


class AdminRegisterSchema(BaseModel):
    admin_id: str
    department: DepartmentEnum
    year: YearEnum
    section: str
    password: str


class AdminLoginSchema(BaseModel):
    admin_id: str
    password: str


class StudentLoginSchema(BaseModel):
    roll_number: str
    mobile: str

class StudentRegisterSchema(BaseModel):
    roll_number: str
    name: str
    department: str
    year: str
    section: str
    mobile: str
    is_cr: bool = False

class SemesterCreateSchema(BaseModel):
    start_date: date
    end_date: date


class SemesterResponseSchema(BaseModel):
    start_date: date
    end_date: date

class SlotCreateSchema(BaseModel):
    slot_number: int
    start_time: time
    end_time: time

class DailyAttendanceScanSchema(BaseModel):
    student_roll: str

class CRManualAttendanceItem(BaseModel):
    roll_number: str
    status: str  # PRESENT or OD

class CRManualAttendanceBulkSchema(BaseModel):
    records: List[CRManualAttendanceItem]


class CRAttendanceEditRecord(BaseModel):
    roll_number: str
    status: str  # PRESENT | OD | ABSENT


class CRAttendanceEditBulkSchema(BaseModel):
    date: date
    records: List[CRAttendanceEditRecord]



class GrievanceCreateSchema(BaseModel):
    grievance_type: str
    request_date: date
    slot: Optional[str] = None
    description: str


class GrievanceDecisionSchema(BaseModel):
    decision: str
    remarks: Optional[str] = None


# -------------------- Timetable module (Admin) --------------------
class SubjectCreateSchema(BaseModel):
    code: str
    name: str


class SubjectListItemSchema(BaseModel):
    id: int
    code: str
    name: str


class TimeSlotCreateSchema(BaseModel):
    # Timetable uses TimeSlot.slot_name; DB stores start_time/end_time and admin_id
    slot_name: str
    start_time: time
    end_time: time


class TimeSlotListItemSchema(BaseModel):
    id: int
    slot_name: str
    start_time: str
    end_time: str


class WeeklyTimetableCellSchema(BaseModel):
    day: str  # Monday..Friday
    slot_id: int
    subject_id: Optional[int] = None


class WeeklyTimetableUpsertSchema(BaseModel):
    cells: List[WeeklyTimetableCellSchema]


class WeeklyTimetableResponseSchema(BaseModel):
    timetable: List[WeeklyTimetableCellSchema]


# -------------------- CR Assignment (Admin) --------------------
class CRAssignmentCurrentUpsertSchema(BaseModel):
    current_cr_student_id: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class CRAssignmentBackupUpsertSchema(BaseModel):
    backup_cr_student_id: Optional[int] = None


class CRAssignmentRemoveSchema(BaseModel):
    pass


