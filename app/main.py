from fastapi import FastAPI


from .database import engine
from .router import rooms, groups, faculty, subjects

from . import models

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(rooms.router)
app.include_router(groups.router)
app.include_router(faculty.router)
app.include_router(subjects.router)
