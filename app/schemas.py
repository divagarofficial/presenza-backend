#prazenza-backend/app/schemas.py
from pydantic import BaseModel
from enum import Enum
from pydantic import BaseModel
from datetime import date, time





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