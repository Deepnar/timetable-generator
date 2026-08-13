#!/usr/bin/env python3
"""Build info/import/synthetic_branches.json — per-branch faculty + rooms.

Teachers are branch-bound; the website publishes a full roster for COMP (~39
members) but none for the other branches. This generator gives EVERY branch a
dedicated faculty pool the same size as COMP's real one (~40), and a per-branch
room pool (real grid rooms + 16 classrooms on floors 1/5/6/7 + 8 labs on floor
3), so the solver never shares a teacher across branches.

COMP uses the real roster names (info/04-faculty-directory.md); the other five
branches get deterministic synthesized Indian engineering faculty names.

Output: info/import/synthetic_branches.json (see info/import-format.md).
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
INFO = os.path.dirname(HERE)  # the repo root's ../info? no — scripts/ is under repo root
INFO = os.path.join(os.path.dirname(HERE))  # repo root
INFO_DIR = os.path.join(INFO, "info", "import")

BRANCHES = ["COMP", "IT", "EXTC", "E&CS", "MECH", "CIVIL"]
TARGET = 40
CR_PER_BRANCH = 16
LAB_PER_BRANCH = 8

REAL_COMP = [
    "Dr. R. R. Sedamkar", "Dr. Sheetal Rathi", "Dr. Rashmi Thakur",
    "Dr. Vaishali Kaiche", "Dr. Shailesh Sangle", "Dr. Harshali P. Patil",
    "Dr. Rekha Sharma", "Mr. Vikas Singh", "Mrs. Lydia Suganya",
    "Mrs. Veena Kulkarni", "Mrs. Deepali Joshi", "Dr. Loukik Salvi",
    "Ms. Foram Shah", "Ms. Siddhi Ambre", "Ms. Tanmayi Nagale",
    "Ms. Drashti Shrimal", "Ms. Pratiksha Deshmukh", "Mr. Swapnil Bhagat",
    "Mr. Ashish Dwivedi", "Ms. Abhilasha Patil", "Mrs. Vinitta Sunish",
    "Ms. Akshata Raut", "Mr. Sudhir Mundhra", "Mr. Shubham Parnekar",
    "Mr. Parth Mehta", "Mr. Samir Sawant", "Mr. Shushant Sawant",
    "Ms. Roshani Baikar", "Mr. Venkatesh Jamardarkhana", "Ms. Neha Wankhede",
    "Dr. Garima Joshi", "Mr. Rishab Singh", "Ms. Vrunal Gharat",
    "Mr. Pankaj Singh", "Mr. Sushil Vichare", "Mr. Deepak Vijaykumar Pal",
    "Dr. Megharani Patil",
]

TITLES = ["Dr.", "Mr.", "Mrs.", "Ms."]
FIRST = [
    "Aarav", "Priya", "Rohan", "Sneha", "Kiran", "Meera", "Aditya", "Ananya",
    "Vikram", "Kavita", "Nikhil", "Pooja", "Rahul", "Shreya", "Sandeep", "Neha",
    "Amit", "Ritu", "Gaurav", "Divya", "Om", "Ishaan", "Tanvi", "Sahil", "Riya",
    "Arjun", "Karan", "Nisha", "Dev", "Sana", "Rakesh", "Megha", "Siddharth",
    "Anushka", "Pranav", "Shraddha", "Aditi", "Kunal", "Vaishali", "Harsha",
    "Yash", "Mrunal", "Abhishek", "Pooja", "Kshitij", "Revati", "Nitin", "Sonali",
    "Amol", "Prajakta",
]
LAST = [
    "Patel", "Sharma", "Iyer", "Kulkarni", "Desai", "Joshi", "Rao", "Nair",
    "Gupta", "Mehta", "Singh", "Reddy", "Bhat", "Fernandes", "Chauhan", "Naik",
    "Pillai", "Hegde", "Thakur", "More", "Kadam", "Pawar", "Sawant", "Gavde",
    "Salunkhe", "Tiwari", "Verma", "Das", "Chavan", "Jadhav", "Waghmare",
    "Bhosale", "Gokhale", "Kale", "Patil", "Shinde", "Apte", "Datar",
]


def synth_names(code: str, count: int) -> list[str]:
    rng = random.Random(hash(code) & 0xFFFF)
    seen = set()
    out = []
    while len(out) < count:
        n = f"{rng.choice(TITLES)} {rng.choice(FIRST)} {rng.choice(LAST)}"
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def main() -> int:
    with open(os.path.join(INFO_DIR, "rooms.json")) as f:
        real_rooms = json.load(f)["rooms"]

    faculty = []
    rooms = []
    for code in BRANCHES:
        names = REAL_COMP if code == "COMP" else []
        if len(names) < TARGET:
            names = names + synth_names(code, TARGET - len(names))
        for nm in names:
            faculty.append({"department_code": code, "name": nm})
        # Real grid rooms for this branch.
        for r in real_rooms:
            if r.get("department_code") == code:
                cap = r.get("capacity") or (45 if r.get("room_type") == "LAB" else 80)
                floor = int(str(r["name"])[0]) if str(r["name"])[0].isdigit() else 1
                rooms.append({"department_code": code, "name": r["name"],
                              "room_type": r.get("room_type") or "CLASSROOM",
                              "capacity": cap, "floor": floor})
        # 16 classrooms (floors 1/5/6/7) + 8 labs (floor 3).
        for n in range(1, CR_PER_BRANCH + 1):
            floor = [1, 5, 6, 7][(n - 1) % 4]
            rooms.append({"department_code": code, "name": f"{code}-CR-{n}",
                          "room_type": "CLASSROOM", "capacity": 80, "floor": floor})
        for n in range(1, LAB_PER_BRANCH + 1):
            rooms.append({"department_code": code, "name": f"{code}-LAB-{n}",
                          "room_type": "LAB", "capacity": 45, "floor": 3})

    data = {"generated_from": "COMP real roster scale", "faculty": faculty, "rooms": rooms}
    with open(os.path.join(INFO_DIR, "synthetic_branches.json"), "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    per = {}
    for code in BRANCHES:
        per[code] = (sum(1 for x in faculty if x["department_code"] == code),
                     sum(1 for x in rooms if x["department_code"] == code))
    print("synthetic_branches.json written.")
    for code, (f, r) in per.items():
        print(f"  {code}: {f} faculty, {r} rooms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
