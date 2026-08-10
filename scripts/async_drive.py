"""Drive an async generation through the real Celery worker + Redis."""
import time
import httpx

BASE = "http://localhost:8000"


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30)
    r = client.post("auth/login", json={
        "email": "admin@example.com", "password": "admin123"})
    r.raise_for_status()
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    profs = client.get("api/v1/profiles/", params={"limit": 200}, headers=headers).json()
    pid = next(p["id"] for p in profs if p["name"] == "Information Technology — All Sems")

    r = client.post("api/v1/generate/", headers=headers, json={
        "profile_id": pid, "timetable_type": "CLASS", "academic_year": "2026-27",
        "instances_requested": 1, "algorithm": "GREEDY"})
    print(f"POST /generate (async) -> {r.status_code}")
    body = r.json()
    gid = body["id"]
    print(f"  run id={gid} status={body['generation_status']}")

    if r.status_code != 202:
        print("  not async; run is:", body)
        return 1

    for attempt in range(30):
        time.sleep(2)
        s = client.get(f"api/v1/generate/{gid}/status", headers=headers).json()
        print(f"  poll[{attempt * 2 + 2}s] {s['generation_status']} "
              f"(instances={s['instances_produced']}, dur_ms={s.get('run_duration_ms')})")
        if s["generation_status"] in ("COMPLETED", "FAILED"):
            if s["generation_status"] == "FAILED":
                print("  error_log:", s.get("error_log"))
            insts = client.get(f"api/v1/instances/{gid}", headers=headers).json()
            print(f"  instances: {len(insts)}")
            for i in insts:
                slots = client.get(f"api/v1/instances/{i['id']}/slots", headers=headers).json()
                print(f"    instance {i['id']}: {len(slots)} slots")
            return 0 if s["generation_status"] == "COMPLETED" else 1
    print("  timed out polling")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
