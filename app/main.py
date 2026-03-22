from fastapi import FastAPI

from .database import engine, Base
from . import models
from .router import rooms, groups, faculty, subjects, room_blackout, faculty_availibility, auth, profiles, constraints, generate, instances

app = FastAPI(title="Timetable Generator API")
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