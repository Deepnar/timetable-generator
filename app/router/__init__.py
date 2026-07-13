"""Router package."""
from . import (
    groups, rooms, faculty, subjects, room_blackout,
    faculty_availibility, auth, profiles, constraints,
    generate, instances, import_csv, history, reset, export,
    settings, assignments,
)

__all__ = [
    "groups", "rooms", "faculty", "subjects", "room_blackout",
    "faculty_availibility", "auth", "profiles", "constraints",
    "generate", "instances", "import_csv", "history", "reset",
    "export", "settings", "assignments",
]
