#presenza-backend/app/security.py
from fastapi.security import HTTPBearer
from jose import jwt, JWTError
import os

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

security = HTTPBearer()
