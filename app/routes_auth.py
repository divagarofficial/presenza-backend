#presenza-backend/app/routes_auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from .database import SessionLocal
from .models import Student, Admin
from .auth import hash_password, verify_password, create_access_token
from .schemas import (
    AdminRegisterSchema,
    AdminLoginSchema,
    StudentLoginSchema
)
from fastapi.security import OAuth2PasswordRequestForm
router = APIRouter(prefix="/auth", tags=["Authentication"])


# -------------------- DB DEPENDENCY --------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------- ADMIN REGISTER --------------------
@router.post("/admin/register")
def admin_register(
    data: AdminRegisterSchema,
    db: Session = Depends(get_db)
):
    # Check if admin already exists
    if db.query(Admin).filter(Admin.admin_id == data.admin_id).first():
        raise HTTPException(status_code=400, detail="Admin already exists")

    admin = Admin(
        admin_id=data.admin_id,
        department=data.department.value,  # Enum → string
        year=data.year.value,              # Enum → string
        section=data.section,
        password_hash=hash_password(data.password)
    )

    db.add(admin)
    db.commit()

    return {"message": "Admin registered successfully"}


# -------------------- ADMIN LOGIN --------------------




@router.post("/admin/login")
def admin_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    admin = db.query(Admin).filter(
        Admin.admin_id == form_data.username
    ).first()

    if not admin or not verify_password(form_data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    token = create_access_token({
        "role": "admin",
        "admin_id": admin.admin_id,
        "department": admin.department,
        "year": admin.year,
        "section": admin.section
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }



# -------------------- STUDENT LOGIN --------------------
@router.post("/student/login")
def student_login(
    data: StudentLoginSchema,
    db: Session = Depends(get_db)
):
    student = db.query(Student).filter(
        Student.roll_number == data.roll_number
    ).first()

    if not student or student.mobile != data.mobile:
        raise HTTPException(
            status_code=401,
            detail="Invalid student credentials"
        )

    token = create_access_token({
        "role": "student",
        "student_id": student.id,
        "roll_number": student.roll_number,
        "is_cr": student.is_cr
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }

