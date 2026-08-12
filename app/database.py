import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

load_dotenv()

# Build the URL via sqlalchemy.engine.URL so credentials are never part of a
# single logged string (security audit H-5): the driver, user, and password are
# separate fields, and SQLAlchemy masks the password in its echo output.
SQLALCHEMY_DATABASE_URL = URL.create(
    "postgresql+psycopg2",
    username=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
