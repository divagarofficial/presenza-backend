#presenza-backend/app/security.py
from fastapi.security import HTTPBearer
from jose import jwt, JWTError
import os

# HS256 needs a non-empty string.
# IMPORTANT: make SECRET_KEY deterministic to avoid intermittent 401 after refresh.
SECRET_KEY = "presenza-dev-only-secret-min-32-chars-change-in-prod!!"
ALGORITHM = "HS256"


security = HTTPBearer()
