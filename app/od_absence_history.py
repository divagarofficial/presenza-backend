from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from sqlalchemy.orm import Session

from .models import ODRequest, AbsenceRequest


def _normalize_date(d: date | str | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, str):
        return d
    return d.isoformat()


def get_student_od_history(db: Session, student_id: int) -> list[dict]:
    rows = (
        db.query(ODRequest)
        .filter(ODRequest.student_id == student_id)
        .order_by(ODRequest.request_date.desc())
        .all()
    )

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "request_date": _normalize_date(r.request_date),
                "date": _normalize_date(r.request_date),
                "category": r.category,
                "slots": r.slots,
                "reason": r.reason,
                "status": r.status,
                "proof_url": r.proof_url,
                "cr_remarks": r.cr_remarks,
            }
        )
    return out


def get_student_absence_history(db: Session, student_id: int) -> list[dict]:
    rows = (
        db.query(AbsenceRequest)
        .filter(AbsenceRequest.student_id == student_id)
        .order_by(AbsenceRequest.request_date.desc())
        .all()
    )

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "request_date": _normalize_date(r.request_date),
                "date": _normalize_date(r.request_date),
                "category": r.category,
                "slots": r.slots,
                "reason": r.reason,
                "status": r.status,
                "proof_url": r.proof_url,
                "cr_remarks": r.cr_remarks,
            }
        )
    return out

