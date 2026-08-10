"""Drive the live API against the seeded dataset: generate, inspect, publish."""
import httpx

BASE = "http://localhost:8000"


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=120)
    r = client.post("auth/login", json={
        "email": "admin@example.com", "password": "admin123"})
    r.raise_for_status()
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # find COMP all-sems profile
    profs = client.get(f"api/v1/profiles/", params={"limit": 200},
                      headers=headers).json()
    pid = next(p["id"] for p in profs if p["name"] == "Computer Engineering — All Sems")
    print(f"COMP all-sems profile id: {pid}")

    gid = None
    # generate via API (greedy, 1 instance) — synchronous
    r = client.post(f"api/v1/generate/", headers=headers, json={
        "profile_id": pid, "timetable_type": "CLASS", "academic_year": "2026-27",
        "instances_requested": 1, "algorithm": "GREEDY"})
    print(f"POST /generate -> {r.status_code}")
    gid = r.json()["id"]
    print(f"  run id={gid} status={r.json()['generation_status']} "
          f"instances={r.json()['instances_produced']}")

    status = client.get(f"api/v1/generate/{gid}/status", headers=headers).json()
    print(f"status endpoint: {status['generation_status']} "
          f"(dur_ms={status.get('run_duration_ms')}, score={status['score_best_instance']})")

    insts = client.get(f"api/v1/instances/{gid}", headers=headers).json()
    print(f"instances: {len(insts)}")
    for i in insts:
        print(f"  instance {i['id']} (#{i['instance_number']}) status={i['status']} "
              f"violations={i['hard_violations']}")
        slots = client.get(f"api/v1/instances/{i['id']}/slots", headers=headers).json()
        print(f"    slots: {len(slots)}")

    if insts:
        inst_id = insts[0]["id"]
        sel = client.post(f"api/v1/instances/{inst_id}/select", headers=headers)
        print(f"select instance {inst_id} -> {sel.status_code} ({sel.json()['status']})")
        pub = client.post(f"api/v1/instances/{inst_id}/publish", headers=headers)
        print(f"publish instance {inst_id} -> {pub.status_code} ({pub.json()['status']})")

    # export endpoints against the published instance
    if insts:
        inst_id = insts[0]["id"]
        for ext in ("csv", "ical"):
            ex = client.get(f"api/v1/export/instances/{inst_id}/{ext}",
                           params={"term_start": "2026-07-06"}, headers=headers)
            print(f"export {ext} -> {ex.status_code} ({len(ex.content)} bytes)")
        pdf = client.get(f"api/v1/export/instances/{inst_id}/pdf", headers=headers)
        print(f"export pdf -> {pdf.status_code} ({len(pdf.content)} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
