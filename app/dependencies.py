#presenza-backend/app/dependencies.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.security import SECRET_KEY, ALGORITHM
from app.database import SessionLocal
from app.models import Student

security = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def admin_required(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admins only")

        return payload

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt, JWTError

def student_required(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        print("JWT PAYLOAD:", payload)

        if payload.get("role") != "student":
            raise HTTPException(status_code=403, detail="Students only")

        # ✅ NORMALIZED & SAFE RETURN
        return {
            "student_id": payload.get("student_id"),
            "roll_number": payload.get("roll_number"),
            "is_cr": payload.get("is_cr", False),  # ⭐ CR FLAG
            "role": payload.get("role")
        }

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def cr_required(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        if payload.get("role") != "student":
            raise HTTPException(status_code=403, detail="Invalid role")

        student = db.query(Student).filter(
            Student.roll_number == payload.get("roll_number")
        ).first()

        if not student or not student.is_cr:
            raise HTTPException(status_code=403, detail="CR access only")

        return student

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
