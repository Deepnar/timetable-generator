from fastapi import FastAPI


from .database import engine
from .router import rooms, groups, faculty, subjects, room_blackout, faculty_availibility

from . import models

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(rooms.router)
app.include_router(groups.router)
app.include_router(faculty.router)
app.include_router(subjects.router)
app.include_router(room_blackout.router)
app.include_router(faculty_availibility.router)