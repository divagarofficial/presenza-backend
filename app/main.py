# presenza-backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine
from . import models
from .routes_auth import router as auth_router
from .routes_admin import router as admin_router
from .routes_students import router as students_router
from .routes_cr import router as cr_router

# Create DB tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="PRESENZA - Presence Is The Proof")

# ✅ CORRECT CORS CONFIG (JWT + LAN + CSV SAFE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.212.188:5173",  # 🔁 your frontend LAN IP
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
    ],
    expose_headers=["Content-Disposition"],
)

# Routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(students_router)
app.include_router(cr_router)

@app.get("/")
def root():
    return {"message": "PRESENZA backend running"}
