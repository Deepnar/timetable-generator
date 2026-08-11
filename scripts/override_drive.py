"""Verify manual-override revalidation returns 409 on a conflicting move."""
import httpx

BASE = "http://localhost:8000"


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=120)
    tok = c.post("auth/login", json={
        "email": "admin@example.com", "password": "admin123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    profs = c.get("api/v1/profiles/", params={"limit": 200}, headers=h).json()
    pid = next(p["id"] for p in profs if p["name"] == "Computer Engineering — Sem 5")
    r = c.post("api/v1/generate/", headers=h, json={
        "profile_id": pid, "timetable_type": "CLASS", "academic_year": "2026-27",
        "instances_requested": 1, "algorithm": "GREEDY"})
    gid = r.json()["id"]
    inst = c.get(f"api/v1/instances/{gid}", headers=h).json()[0]
    slots = c.get(f"api/v1/instances/{inst['id']}/slots", headers=h).json()
    print(f"run {gid}, instance {inst['id']}, {len(slots)} slots")

    s = slots[0]
    print("slot0:", {k: s[k] for k in (
        "id", "day_of_week", "slot_number", "room_id",
        "subject_id", "student_group_id")})

    # Deliberately move it onto another group's (day, slot) → must conflict.
    occupied = {
        (x["student_group_id"], x["day_of_week"], x["slot_number"])
        for x in slots if x["student_group_id"] != s["student_group_id"]
    }
    g2, d2, sn2 = next(iter(occupied))
    r2 = c.patch(f"api/v1/instances/{inst['id']}/slots/{s['id']}", headers=h, json={
        "day_of_week": d2, "slot_number": sn2,
        "override_reason": "move onto another group's slot"})
    print(f"conflicting override -> {r2.status_code}: {r2.text[:140]}")

    # A no-op override (same values) must be accepted.
    r3 = c.patch(f"api/v1/instances/{inst['id']}/slots/{s['id']}", headers=h, json={
        "override_reason": "no-op move"})
    print(f"no-op override -> {r3.status_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
