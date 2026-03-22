from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from . import models
from .router import rooms, groups, faculty, subjects, room_blackout, faculty_availibility, auth, profiles, constraints, generate, instances, import_csv, history, reset

app = FastAPI(title="Timetable Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(faculty.router)
app.include_router(groups.router)
app.include_router(subjects.router)
app.include_router(room_blackout.router)
app.include_router(faculty_availibility.router)
app.include_router(profiles.router)
app.include_router(constraints.router)
app.include_router(generate.router)
app.include_router(instances.router)
app.include_router(import_csv.router)
app.include_router(history.router)
app.include_router(reset.router)