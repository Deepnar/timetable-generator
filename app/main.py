from fastapi import FastAPI

from .database import engine, Base
from . import models
from .router import rooms, groups, faculty, subjects, room_blackout, faculty_availibility

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Timetable Generator API")
app.include_router(rooms.router)
app.include_router(groups.router)
app.include_router(faculty.router)
app.include_router(subjects.router)
app.include_router(room_blackout.router)
app.include_router(faculty_availibility.router)