from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import SessionLocal
from app.models import Admin, Student, Notification
from app.dependencies import admin_required, student_required, cr_required


router = APIRouter(tags=["Notifications"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------- ADMIN --------------------
@router.get("/admin/notifications")
def admin_list_notifications(
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    notes = (
        db.query(Notification)
        .filter(Notification.recipient_admin_id == admin["admin_id"])
        .order_by(desc(Notification.created_at))
        .limit(100)
        .all()
    )

    return {
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "notification_type": n.notification_type,
                "meta": n.meta,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ],
    }


@router.post("/admin/notifications/{notification_id}/read")
def admin_mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    admin=Depends(admin_required),
):
    n = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.recipient_admin_id == admin["admin_id"],
        )
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")

    n.is_read = True
    db.commit()

    return {"message": "Notification marked as read"}


# -------------------- STUDENT --------------------
@router.get("/students/notifications")
def student_list_notifications(
    db: Session = Depends(get_db),
    user=Depends(student_required),
):
    sid = user["student_id"]
    notes = (
        db.query(Notification)
        .filter(Notification.recipient_student_id == sid)
        .order_by(desc(Notification.created_at))
        .limit(200)
        .all()
    )

    return {
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "notification_type": n.notification_type,
                "meta": n.meta,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ],
    }


@router.post("/students/notifications/{notification_id}/read")
def student_mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user=Depends(student_required),
):
    sid = user["student_id"]

    n = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.recipient_student_id == sid,
        )
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")

    n.is_read = True
    db.commit()

    return {"message": "Notification marked as read"}


# -------------------- CR (same as student endpoint, but separate router prefix) --------------------
@router.get("/cr/notifications")
def cr_list_notifications(
    db: Session = Depends(get_db),
    cr=Depends(cr_required),
):
    sid = cr["student_id"]
    notes = (
        db.query(Notification)
        .filter(Notification.recipient_student_id == sid)
        .order_by(desc(Notification.created_at))
        .limit(200)
        .all()
    )

    return {
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "notification_type": n.notification_type,
                "meta": n.meta,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ],
    }


@router.post("/cr/notifications/{notification_id}/read")
def cr_mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    cr=Depends(cr_required),
):
    sid = cr["student_id"]

    n = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.recipient_student_id == sid,
        )
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")

    n.is_read = True
    db.commit()

    return {"message": "Notification marked as read"}

