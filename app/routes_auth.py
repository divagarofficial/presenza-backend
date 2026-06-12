#presenza-backend/app/routes_auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from .database import SessionLocal
from .models import Student, Admin
from .auth import hash_password, verify_password, create_access_token, create_refresh_token
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

    refresh_token = create_refresh_token({
        "role": "admin",
        "admin_id": admin.admin_id,
        "department": admin.department,
        "year": admin.year,
        "section": admin.section
    })

    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }



# -------------------- REFRESH TOKEN --------------------
from pydantic import BaseModel


class RefreshTokenBody(BaseModel):
    refresh_token: str


@router.post("/refresh")
def refresh_access_token(
    body: RefreshTokenBody
):
    refresh_token = body.refresh_token
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token is required")


    try:
        from jose import jwt
        from .auth import create_access_token
        from app.security import SECRET_KEY, ALGORITHM

        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type = payload.get("type")
        if token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        role = payload.get("role")
        if role == "admin":
            access = create_access_token({
                "role": "admin",
                "admin_id": payload.get("admin_id"),
                "department": payload.get("department"),
                "year": payload.get("year"),
                "section": payload.get("section"),
            })
        elif role == "student":
            access = create_access_token({
                "role": "student",
                "student_id": payload.get("student_id"),
                "roll_number": payload.get("roll_number"),
                "is_cr": payload.get("is_cr", False),
            })
        else:
            raise HTTPException(status_code=401, detail="Invalid refresh token role")

        return {"access_token": access, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Refresh failed: {type(e).__name__}")



# -------------------- STUDENT LOGIN --------------------
@router.post("/student/login")
def student_login(

    data: StudentLoginSchema,
    db: Session = Depends(get_db)
):
    roll = (data.roll_number or "").strip()
    mobile = (data.mobile or "").strip()

    student = db.query(Student).filter(Student.roll_number == roll).first()

    if not student:
        raise HTTPException(
            status_code=401,
            detail="Invalid student credentials (no student with this roll number — register locally first)",
        )

    if (student.mobile or "").strip() != mobile:
        raise HTTPException(
            status_code=401,
            detail="Invalid student credentials (mobile does not match the one used at registration)",
        )

    token = create_access_token({
        "role": "student",
        "student_id": student.id,
        "roll_number": student.roll_number,
        "is_cr": student.is_cr
    })

    refresh_token = create_refresh_token({
        "role": "student",
        "student_id": student.id,
        "roll_number": student.roll_number,
        "is_cr": student.is_cr
    })

    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


