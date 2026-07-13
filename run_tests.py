import httpx
import json

BASE_URL = "http://localhost:8000"

print(f"🔌 Connecting to {BASE_URL}/docs ...")

def test_auth():
    print("\n1️⃣ TESTING AUTH LOGIN")
    r = httpx.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@example.com",
        "password": "admin123"
    })
    if r.status_code != 200:
        print(f"   ❌ Login failed: {r.text}")
        return None
    token = r.json()["access_token"]
    print(f"   ✅ Logged in successfully!")
    return f"Bearer {token}"

def test_rooms(token):
    print("\n2️⃣ TESTING ROOMS CRUD")
    # Create
    headers = {"Authorization": token}
    payload = {
        "name": "Test Lab A",
        "room_code": "TLA-101",
        "room_type": "LAB",
        "capacity": 50,
        "building": "Block C"
    }
    r = httpx.post(f"{BASE_URL}/rooms/", json=payload, headers=headers)
    if r.status_code == 201:
        print("   ✅ Room created successfully")
    else:
        print(f"   ❌ Room creation failed: {r.text}")

def test_subjects(token):
    print("\n3️⃣ TESTING SUBJECTS CRUD")
    headers = {"Authorization": token}
    payload = {
        "name": "Data Structures",
        "subject_code": "CS-201",
        "department": "Computer Science",
        "semester": 3,
        "hours_per_week": 4,
        "requires_lab": True
    }
    r = httpx.post(f"{BASE_URL}/subjects/", json=payload, headers=headers)
    if r.status_code == 201:
        print("   ✅ Subject created successfully")
    else:
        print(f"   ❌ Subject creation failed: {r.text}")

def test_groups(token):
    print("\n4️⃣ TESTING STUDENT GROUPS CRUD")
    headers = {"Authorization": token}
    payload = {
        "name": "CS-A",
        "group_type": "DIVISION",
        "department": "Computer Science",
        "year": 2,
        "semester": 3,
        "strength": 60
    }
    r = httpx.post(f"{BASE_URL}/groups/", json=payload, headers=headers)
    if r.status_code == 201:
        print("   ✅ Group created successfully")
    else:
        print(f"   ❌ Group creation failed: {r.text}")

def test_assignments(token):
    print("\n5️⃣ TESTING NEW MAPPING (Subject-Faculty-Group)")
    headers = {"Authorization": token}
    payload = {
        "subject_id": 1,
        "faculty_id": 1,
        "group_id": 1,
        "weekly_hours": 4,
        "load_share": 1.0
    }
    r = httpx.post(f"{BASE_URL}/assignments/", json=payload, headers=headers)
    if r.status_code == 201:
        print("   ✅ Subject assignment mapping created successfully")
    else:
        print(f"   ❌ Mapping creation failed: {r.text}")

def test_health():
    print("\n6️⃣ TESTING HEALTH CHECK")
    try:
        r = httpx.get(f"{BASE_URL}/health")
        if r.status_code == 200:
            print("   ✅ System is healthy!")
        else:
            print(f"   ❌ Health check returned {r.status_code}")
    except Exception as e:
        print(f"   ⚠️ /health endpoint not implemented yet ({e})")

if __name__ == "__main__":
    token = test_auth()
    if token:
        test_rooms(token)
        test_subjects(token)
        test_groups(token)
        test_assignments(token)
    test_health()
