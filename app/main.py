# presenza-backend/app/main.py

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import engine
from . import models
from .routes_auth import router as auth_router
from .routes_admin import router as admin_router
from .routes_students import router as students_router
from .routes_student_holiday_announcements import router as student_holiday_router
from .routes_student_home_announcement import router as student_home_announcement_router


from .routes_cr import router as cr_router
from .routes_notifications import router as notifications_router



# Create DB tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="PRESENZA - Presence Is The Proof")

# ✅ CORRECT CORS CONFIG (JWT + LAN + CSV SAFE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.212.188:5173",
        "https://presenza-frontend.vercel.app",  # 🔁 your frontend LAN IP
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
app.include_router(notifications_router)


# IMPORTANT: some frontend routes are implemented as React routes; backend does not serve them.
# Avoid adding placeholder HTML routes that can shadow /admin/* APIs.

app.include_router(students_router)
app.include_router(cr_router)
app.include_router(student_holiday_router)
app.include_router(student_home_announcement_router)





static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    return {"message": "PRESENZA backend running"}
