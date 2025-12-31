#prazenza-backend/app/utils/qr.py
import time
import hmac
import hashlib
from datetime import date, timedelta

from app.models import QRSession


def generate_dynamic_qr(secret: str):
    window = int(time.time() / 3)
    msg = f"{secret}:{window}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def cleanup_old_qr(db):
    yesterday = date.today() - timedelta(days=1)
    db.query(QRSession).filter(QRSession.date < yesterday).delete()
    db.commit()


def validate_dynamic_qr(secret: str, qr_value: str) -> bool:
    current_window = int(time.time() / 3)

    for offset in [-1, 0, 1]:  # tolerance window
        msg = f"{secret}:{current_window + offset}".encode()
        expected = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

        if hmac.compare_digest(expected, qr_value):
            return True

    return False
