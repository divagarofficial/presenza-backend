#presenza-backend/app/dependencies.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.security import SECRET_KEY, ALGORITHM
from app.database import SessionLocal
from app.models import Student, CRAssignment


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

    except JWTError as e:
        # jose can fail due to exp/nbf/signature/claims mismatch
        raise HTTPException(status_code=401, detail=f"Invalid token: {type(e).__name__}: {str(e)}")




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

        # Assignment gating: ensure this CR (or backup) is active for the CR's section
        today = None
        try:
            from datetime import date
            today = date.today()
        except Exception:
            today = None

        assignment = (
            db.query(CRAssignment)
            .filter(
                CRAssignment.department == student.department,
                CRAssignment.year == student.year,
                CRAssignment.section == student.section,
            )
            .first()
        )

        is_assigned = False
        if assignment and today:
            # Current CR validity
            if assignment.current_cr_student_id == student.id:
                if (assignment.valid_from is None or assignment.valid_from <= today) and (
                    assignment.valid_to is None or assignment.valid_to >= today
                ):
                    is_assigned = True

            # Backup CR only if current CR is not active OR no current assigned
            if not is_assigned and assignment.backup_cr_student_id == student.id:
                current_active = False
                if assignment.current_cr_student_id is not None:
                    if (assignment.valid_from is None or assignment.valid_from <= today) and (
                        assignment.valid_to is None or assignment.valid_to >= today
                    ):
                        current_active = True
                if assignment.current_cr_student_id is None or not current_active:
                    is_assigned = True

        if not is_assigned:
            raise HTTPException(status_code=403, detail="CR not assigned for this section")

        return {
            "student_id": student.id,
            "roll_number": student.roll_number,
            "is_cr": student.is_cr,
            "department": student.department,
            "year": student.year,
            "section": student.section,
        }


    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
