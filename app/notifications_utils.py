from __future__ import annotations

from datetime import datetime, date
from sqlalchemy.orm import Session

from app.models import Notification, Student, Admin


def _ensure_notification_target(db: Session, student_id: int | None = None, admin_id: str | None = None):
    if student_id is None and admin_id is None:
        return


def create_notification_for_admin(
    db: Session,
    *,
    target_department: str,
    target_year: str,
    target_section: str,
    message: str,
    notification_type: str,
    meta: dict | None = None,
):
    admins = (
        db.query(Admin)
        .filter(
            Admin.department == target_department,
            Admin.year == target_year,
            Admin.section == target_section,
        )
        .all()
    )

    for a in admins:
        n = Notification(
            recipient_admin_id=a.admin_id,
            recipient_student_id=None,
            recipient_role="admin",
            message=message,
            notification_type=notification_type,
            meta=meta,
        )
        db.add(n)

    db.commit()


def create_notification_for_student(
    db: Session,
    *,
    student_id: int,
    message: str,
    notification_type: str,
    meta: dict | None = None,
):
    n = Notification(
        recipient_admin_id=None,
        recipient_student_id=student_id,
        recipient_role="student",
        message=message,
        notification_type=notification_type,
        meta=meta,
    )
    db.add(n)
    db.commit()


def create_notification_for_students_in_section(
    db: Session,
    *,
    department: str,
    year: str,
    section: str,
    message: str,
    notification_type: str,
    meta: dict | None = None,
):
    students = (
        db.query(Student)
        .filter(
            Student.department == department,
            Student.year == year,
            Student.section == section,
        )
        .all()
    )

    for s in students:
        create_notification_for_student(
            db,
            student_id=s.id,
            message=message,
            notification_type=notification_type,
            meta=meta,
        )


