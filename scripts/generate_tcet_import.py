#!/usr/bin/env python3
"""Generate info/import/*.json per info/import-format.md spec.

Reads the vision-verified markdown in info/03-timetables/class/UG/ plus the
institute/academic-calendar docs. Never invents data: missing -> null / _note.
"""
import json, os, re, sys

ROOT = "/home/deepnar/Programs/timetable-api/info"
UG = os.path.join(ROOT, "03-timetables/class/UG")
OUT = os.path.join(ROOT, "import")
os.makedirs(OUT, exist_ok=True)

AY = "2026-27"

# --------------------------------------------------------------------------
# 1. departments.json
# --------------------------------------------------------------------------
# code -> (name, established, labs, divisions, fe_group, strength notes)
DEPT_META = {
    "COMP":  ("Computer Engineering", "AY 2002-03", {"SE": 4, "TE": 4, "BE": 3}, "I", {"FE": 63}),
    "IT":    ("Information Technology", "AY 2001-02", {"SE": 4, "TE": 3, "BE": 3}, "II", {}),
    "EXTC":  ("Electronics & Telecommunication Engineering", "AY 2001-02", {"SE": 2, "TE": 2, "BE": 2}, "II", {}),
    "E&CS":  ("Electronics & Computer Science", "AY 2020-21", {"SE": 1, "TE": 1, "BE": 1}, "II", {}),
    "MECH":  ("Mechanical Engineering", "AY 2012-13", {"SE": 1, "TE": 1, "BE": 1}, "II", {}),
    "CIVIL": ("Civil Engineering", "AY 2015-16", {"SE": 1, "TE": 1, "BE": 1}, "I", {}),
    "AI&ML": ("Artificial Intelligence & Machine Learning", "AY 2020-21", {"ST": 3, "TT": 1, "BT": 1}, "II", {}),
    "AI&DS": ("Artificial Intelligence & Data Science", "AY 2020-21", None, "I", {}),
    "IoT":   ("Internet of Things", "AY 2021-22", None, "I", {}),   # per esah doc; site ambiguous
    "CSE-IoT": ("Computer Science & Engineering (IoT)", "AY 2021-22", None, "I", {}),
    "CS&E":  ("Computer Science & Engineering (Cyber Security)", "AY 2022-23", None, None, {}),
    "MME":   ("Mechanical & Mechatronics Engineering", "AY 2022-23", None, "II", {}),
    "BCA":   ("Bachelor of Computer Applications", "AY 2024-25", None, None, {}),
    "MCA":   ("Master of Computer Applications", "AY 2025-26", None, None, {}),
    "MBA":   ("Master of Business Administration", None, None, None, {}),
    "ES&H":  ("Engineering Sciences & Humanities", None, None, None, {}),
}
# dept index table: established + labs from 02-departments/README.md
DEPT_LABS = {"aids": "04+01", "aiml": "03", "bba": None, "bca": None, "bvoc": "05",
             "civil": "07", "computer-engineering": "06+01", "cse": None, "extc": None,
             "electronics-cs": None, "humanities-sciences": "18", "iot": None,
             "information-technology": None, "mca": None, "mba": None, "mechanical": "10", "mme": "03"}

departments = []
for code, (name, est, divs, feg, strength) in DEPT_META.items():
    d = {"code": code, "name": name}
    if est:
        d["established"] = est
    if feg:
        d["fe_group"] = feg
    if code == "ES&H":
        d["owns_fe"] = True
        d["labs"] = 18
        d["classrooms"] = 14
        d["_note"] = "ES&H teaches all FE; FE division counts change per intake (COMP 4 this year, 3 last)"
    if divs:
        d["divisions"] = divs
    if strength:
        d["strength"] = strength
    departments.append(d)

json.dump({"academic_year": AY, "departments": departments},
          open(os.path.join(OUT, "departments.json"), "w"), indent=2, ensure_ascii=False)
print("departments.json:", len(departments), "depts")

# --------------------------------------------------------------------------
# helpers: parse the branch README files into structured divisions
# --------------------------------------------------------------------------
def read(p):
    return open(p, encoding="utf-8").read()

_ROMAN = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII"}


def _initials_tokens(paren: str) -> set:
    """Faculty-initial tokens inside a legend paren, e.g. "(SuS / NW)".

    A paren may hold initial/name pairs ("TN = Tanmayi Nagale"), bare initials
    ("LJS, PM"), or a plain word ("online", "multi-faculty"). Return the
    initials only.
    """
    out = set()
    for tok in re.split(r"[/,]", paren):
        tok = tok.strip()
        if not tok:
            continue
        m = re.match(r"^([A-Z][A-Za-z0-9]{0,3})\s*=\s*(.+)$", tok)
        if m:
            ini = m.group(1).strip()
            if len(ini) <= 4 and ini not in _ROMAN and not ini.isdigit():
                out.add(ini)
            continue
        if (re.match(r"^[A-Z][A-Za-z0-9]{0,3}$", tok) and len(tok) <= 4
                and tok not in _ROMAN and not tok.isdigit()):
            out.add(tok)
    return out


def legend_pairs(legend):
    """Extract (code, name) and (code -> set of initials) from a legend line.

    Real legends are ``CODE (INIT = Name / INIT2 = Name2)``, ``CODE (INIT /
    INIT2)``, or ``CODE = Name``. Code stays the name when no name is given.
    """
    pairs, initials = {}, {}
    legend = re.sub(r"\s+", " ", legend).rstrip(" .")
    for s in re.split(r"[·;]", legend):
        s = re.sub(r"^\s*Legend:?\s*", "", s).strip()
        if not s:
            continue
        pm = re.match(r"^([A-Za-z][A-Za-z0-9&/\-\. ]{0,14}?)\s*(?:\((.*)\))?\s*$", s)
        if pm:
            code = pm.group(1).strip()
            paren = pm.group(2)
        else:
            em = re.match(r"^([A-Za-z][A-Za-z0-9&/\-\. ]{0,14}?)\s*=\s*(.+)$", s)
            if not em:
                continue
            code = em.group(1).strip()
            paren = None
            name = re.sub(r"\s*\(.*\)\s*$", "", em.group(2)).strip()
            pairs[code] = name or code
        if not re.match(r"^[A-Z0-9]", code):
            continue
        if paren:
            inn = _initials_tokens(paren)
            if inn:
                initials[code] = inn
        pairs.setdefault(code, code)
    return pairs, initials

def split_entries(cell):
    """A cell may hold 2 parallel entries joined by ' · '."""
    return [e.strip() for e in cell.split("·")]

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}

def parse_cell(entry, legend_codes, legend_initials, glossary_initials):
    """Parse one grid entry -> cell dict."""
    e = entry.strip()
    up = e.upper()
    cell = {"kind": None, "subject": None, "batch": None, "faculty": [], "room": None,
            "online": False, "label": e}
    if not e or e in ("—", "-", "–", ""):
        cell["kind"] = "FREE"
        return cell
    if re.search(r"\bBREAK\b|\bLUNCH\b", up):
        cell["kind"] = "BREAK"
        return cell
    if re.search(r"NOTIONAL|SL/CL|CO-CURRICULAR|EXTRA-CURRICULAR|SELF-LEARNING|LIBRARY|MENTORING", up):
        cell["kind"] = "NOTIONAL"
        return cell
    if re.search(r"\bPROJECT\b|PROJECT-I", up):
        cell["kind"] = "ACTIVITY"
        cell["subject"] = "PROJECT"
        return cell
    if re.search(r"\bIC\b|INDIAN CONSTITUTION", up) and re.search(r"ONLINE|ON-LINE", up):
        cell["kind"] = "ACTIVITY"
        cell["subject"] = "IC"
        cell["online"] = True
        return cell
    # rooms
    rooms = re.findall(r"\b(\d{3})\b", e)
    if rooms:
        cell["room"] = rooms[0]
        if len(rooms) > 1 and "/" in e:
            cell["room"] = "/".join(rooms)
    # batch ids like A1A2 / D1D2 / C3C4 / B1B2 / (A1/A2) / A1 A2
    bm = (re.search(r"\b([A-D])([1-4])\s*/\s*\1\s*([1-4])\b", e)
          or re.search(r"\b([A-D])([1-4])\s*[A-D]?\s*([1-4])\b", e))
    if bm:
        cell["batch"] = [int(bm.group(2)), int(bm.group(3)) if bm.lastindex >= 3 else int(bm.group(2))]
    elif re.search(r"Batch\s*([1-9])\b", e, re.I):
        bs = re.findall(r"Batch\s*([1-9])\b", e, re.I)
        cell["batch"] = [int(b) for b in bs]
    # faculty initials: tokens that appear in legend initials or glossary
    toks = re.findall(r"\b[A-Z][a-z]?[A-Z]?[a-z]?\b", e)
    known = legend_initials | glossary_initials
    fac = [t for t in toks if t in known and len(t) >= 2 and t not in legend_codes]
    if fac:
        cell["faculty"] = fac
    # subject: leading code token matching a legend code
    for t in toks:
        if t in legend_codes:
            cell["subject"] = t
            break
    if cell["subject"] is None:
        # patterns like "Lab DBMS", "M III GS", "OE II PDD", "PE II DA/IS/CC"
        m = re.match(r"^(?:Lab\s+)?([A-Z][A-Za-z0-9&/.\- ]{1,14}?)\s+(?=[A-Z]|\d{3}|$)", e)
        if m:
            cand = m.group(1).strip()
            if cand in legend_codes or cand.split()[0] in legend_codes:
                cell["subject"] = cand if cand in legend_codes else cand.split()[0]
    # kind
    if re.search(r"^\s*Lab\b", e):
        cell["kind"] = "LAB"
    elif re.search(r"TuT|TUT", up):
        cell["kind"] = "TUTORIAL"
    elif re.search(r"ONLINE|ON-LINE", up):
        cell["kind"] = "LECTURE"
        cell["online"] = True
    elif cell["subject"]:
        cell["kind"] = "LECTURE"
    else:
        cell["kind"] = "ACTIVITY"
    return cell

# --------------------------------------------------------------------------
# glossary: initial -> name
# --------------------------------------------------------------------------
GLOSS = {}
gl = read(os.path.join(UG, "FACULTY-INITIALS.md"))
for m in re.finditer(r"^\| ([A-Z][A-Za-z0-9]*(?:/[A-Z][A-Za-z0-9]*)*) \| \d+ \| ([^|]+) \|", gl, re.M):
    for ini in m.group(1).split("/"):
        GLOSS[ini.strip()] = m.group(2).strip()
# unresolved section: bullet list of initials
for m in re.finditer(r"^- `([A-Za-z]+)`", gl, re.M):
    GLOSS.setdefault(m.group(1), "?")
print("glossary initials:", len(GLOSS))

# --------------------------------------------------------------------------
# 8. timetables.json + 6. assignments.json + 3. subjects.json + 4. rooms.json
#    + 5. groups.json  (from the branch READMEs)
# --------------------------------------------------------------------------
BRANCH_FILES = {
    "COMP": "computer-engineering", "IT": "information-technology",
    "EXTC": "extc", "AI&ML": "aiml", "CIVIL": "civil", "E&CS": "electronics-cs",
    "MECH": "mechanical", "BCA": "bca", "MCA": "mca", "MBA": "mba",
    "ES&H": "humanities-sciences",
}

def sem_number(s):
    s = s.upper()
    m = re.search(r"SEM(?:ESTER)?\s*(I{1,3}V?|V?I{0,3})", s)
    if m:
        return ROMAN.get(m.group(1), None)
    m = re.search(r"SEM\s*(\d)", s, re.I)
    return int(m.group(1)) if m else None

def year_from_sem(sem):
    return {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4}.get(sem, None)

timetables, assignments, subjects, rooms, groups = [], [], [], [], []
room_seen = set()

for code, folder in BRANCH_FILES.items():
    fp = os.path.join(UG, folder, "README.md")
    if not os.path.isfile(fp):
        print("MISSING:", fp)
        continue
    txt = read(fp)
    # split into division sections
    sections = re.split(r"\n## ", txt)
    for sec in sections[1:]:
        title_full = sec.split("\n", 1)[0].strip()
        body = sec
        sem = sem_number(title_full)
        if sem is None and code == "MBA":
            sem = 3  # MBA doc header states Sem III; section titles don't repeat it
        if sem is None and code == "AI&ML":
            # AI&ML titles say "T.T. (Third Year)" / "B.T. (Final Year)" — even sem 2025-26
            sem = 6 if "Third" in title_full else (8 if "Final" in title_full else None)
        if sem is None:
            continue
        title = title_full
        if "—" in title and "venue" not in title.lower():
            title = title.split("—")[0].strip()
        # venue + incharge
        vm = re.search(r"[Vv]enue:?\s*([0-9/]+)", body)
        venue = vm.group(1) if vm else None
        im = re.search(r"[Ii]n.?charge:?\s*([^·|\n]+)", body)
        incharge = im.group(1).strip() if im else None
        # legend
        lm = re.search(r"Legend:?\s*(.+?)(?=\n\n|\n\|)", body, re.S)
        legend_codes, legend_initials = ({}, set())
        if lm:
            lc, li = legend_pairs(lm.group(1))
            legend_codes.update(lc)
            for v in li.values():
                legend_initials |= v
        # grid table: first pipe table after the legend
        tm = re.search(r"(\| Day .*?\n(?:\|[-: |]+\n)?((?:\|.*\n)+?))(?=\n## |\n---|\Z)", body, re.S)
        if not tm:
            continue
        header = tm.group(1)
        hdr_cells = [c.strip() for c in header.split("\n")[0].strip("|").split("|")]
        # slots: derive from header times (mon-fri etc.); use slot index if no times
        slot_times = []
        for c in hdr_cells[1:]:
            c = c.replace("–", "-")
            m = re.match(r"\s*(\d{1,2}[:.]\d{2})\s*-\s*(\d{1,2}[:.]\d{2})", c)
            slot_times.append((m.group(1), m.group(2)) if m else None)
        rows = re.findall(r"^\| (MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|MON|TUE|WED|THU|FRI|SAT)\s*\|(.+)$", header, re.M | re.I)
        cells_out = []
        day_map = {"MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4,
                   "SATURDAY": 5, "MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5}
        for dname, rest in rows:
            day = day_map.get(dname.upper())
            if day is None:
                continue
            parts = [p.strip() for p in rest.strip().split("|")]
            for i, p in enumerate(parts):
                for entry in split_entries(p):
                    cell = parse_cell(entry, legend_codes, legend_initials, set(GLOSS))
                    cell["day"] = day
                    cell["slot"] = i + 1
                    cells_out.append(cell)
        group_name = f"{code}-{title.split('(')[0].strip().replace(' ', '-').replace('/', '-')}"
        # de-mangle: drop the branch word that repeats in the title (e.g. "SE COMP A" -> "SE-A")
        g = group_name
        for w in ("COMP", "IT", "E&TC", "EXTC", "AI&ML", "AI", "CIVIL", "E&CS", "MECH", "MBA", "MCA", "BCA"):
            g = re.sub(rf"-{re.escape(w)}-", "-", g)
        g = re.sub(r"-+", "-", g).strip("-")
        group_name = g
        tt = {"group_name": group_name, "academic_year": AY, "semester": sem,
              "cells": cells_out}
        if venue:
            tt["venue"] = venue
        if incharge:
            tt["class_incharge"] = incharge
        timetables.append(tt)
        # groups
        groups.append({"name": group_name, "department_code": code, "year": year_from_sem(sem),
                       "semester": sem, "strength": None, "type": "DIVISION"})
        # rooms from cells
        for c in cells_out:
            if c.get("room"):
                for r in str(c["room"]).split("/"):
                    r = r.strip()
                    if r and r not in room_seen:
                        room_seen.add(r)
                        rooms.append({"department_code": code, "name": r, "room_code": r,
                                      "room_type": "LAB" if re.search(r"^\d+$", r) and int(r) < 200 else "CLASSROOM",
                                      "capacity": None, "_note": "capacity not published on site"})
        # subjects + assignments from legend + grid
        for s_code, s_name in legend_codes.items():
            kind = "LAB" if s_code.startswith(("Lab", "lab")) else "LECTURE"
            subjects.append({"department_code": code, "semester": sem, "name": s_name,
                             "code": s_code, "kind": kind, "hours_per_week": None,
                             "room_type": "LAB" if kind == "LAB" else "CLASSROOM",
                             "min_capacity": None, "is_online": False})
        if code == "MBA":
            # MBA grids carry full course names, no abbreviations
            seen_mba = set()
            for c in cells_out:
                if c["kind"] in ("LECTURE", "ACTIVITY") and c.get("label") and c["label"] not in seen_mba:
                    seen_mba.add(c["label"])
                    subjects.append({"department_code": "MBA", "semester": 3, "name": c["label"],
                                     "code": c["label"], "kind": "LECTURE", "hours_per_week": None,
                                     "room_type": "CLASSROOM", "min_capacity": None, "is_online": False,
                                     "_note": "course name used as code (MBA grids have no abbreviations)"})

json.dump({"timetables": timetables}, open(os.path.join(OUT, "timetables.json"), "w"),
          indent=1, ensure_ascii=False)

# 6. assignments.json — whole-division from legends + per-batch from lab cells
assign_rows = []
seen_asg = set()
period_counter: dict = {}
for tt in timetables:
    code = tt["group_name"].split("-")[0]
    sem = tt["semester"]
    gname = tt["group_name"]
    for c in tt["cells"]:
        subj = c.get("subject")
        if not subj or c["kind"] in ("NOTIONAL", "BREAK", "FREE"):
            continue
        fac = c.get("faculty") or []
        if c["kind"] == "LAB" and c.get("batch"):
            # Each LAB cell is ONE weekly period (a set of parallel batches).
            pc = period_counter.get((gname, subj), 0) + 1
            period_counter[(gname, subj)] = pc
            # one row per batch, faculty mapped by position (fallback: all faculty for batch 1)
            for b in c["batch"]:
                f = fac[min(b - 1, len(fac) - 1)] if fac else None
                key = (gname, subj, b, f)
                if key in seen_asg:
                    continue
                seen_asg.add(key)
                row = {"subject_code": subj, "group_name": gname, "faculty_initials": f,
                       "weekly_hours": None, "batch_number": b, "period_id": pc,
                       "_note": "hours_per_week null — derive from grid slot count"}
                if f and f in GLOSS and GLOSS[f] != "?" and ";" not in GLOSS[f]:
                    row["faculty_name"] = GLOSS[f]
                assignments.append(row)
        else:
            for f in fac:
                key = (gname, subj, None, f)
                if key in seen_asg:
                    continue
                seen_asg.add(key)
                row = {"subject_code": subj, "group_name": gname, "faculty_initials": f,
                       "weekly_hours": None, "batch_number": None}
                if f and f in GLOSS and GLOSS[f] != "?" and ";" not in GLOSS[f]:
                    row["faculty_name"] = GLOSS[f]
                assignments.append(row)
json.dump({"assignments": assignments}, open(os.path.join(OUT, "assignments.json"), "w"),
          indent=1, ensure_ascii=False)
print("assignments:", len(assignments))
json.dump({"groups": groups}, open(os.path.join(OUT, "groups.json"), "w"),
          indent=1, ensure_ascii=False)
json.dump({"rooms": rooms}, open(os.path.join(OUT, "rooms.json"), "w"),
          indent=1, ensure_ascii=False)
# dedupe subjects (same dept+sem+code+kind across divisions)
seen_sub = set()
dedup = []
for s in subjects:
    k = (s["department_code"], s["semester"], s["code"], s["kind"])
    if k not in seen_sub:
        seen_sub.add(k)
        dedup.append(s)
subjects = dedup
json.dump({"subjects": subjects}, open(os.path.join(OUT, "subjects.json"), "w"),
          indent=1, ensure_ascii=False)
print("timetables:", len(timetables), "| groups:", len(groups), "| rooms:", len(rooms), "| subjects:", len(subjects))

# --------------------------------------------------------------------------
# 2. faculty.json — from glossary + rosters
# --------------------------------------------------------------------------
faculty_rows = []
seen_names = {}
for ini, nm in sorted(GLOSS.items()):
    if nm and nm != "?" and not nm.startswith("(") and ";" not in nm:
        key = nm
        if key in seen_names:
            seen_names[key]["initials"].append(ini)
        else:
            seen_names[key] = {"name": nm, "initials": [ini]}
    else:
        note = "unresolved initial" if (not nm or nm == "?") else "ambiguous initial — multiple candidates in glossary"
        faculty_rows.append({"name": None, "initials": [ini], "_note": note, "candidates": nm if nm and nm != "?" else None})
for nm, d in seen_names.items():
    d["initials"] = sorted(set(d["initials"]))
    faculty_rows.append(d)
# dept assignment from rosters where possible
rosters = {"COMP": "computer-engineering", "IT": "information-technology",
           "EXTC": "extc", "AI&ML": "aiml", "CIVIL": "civil", "E&CS": "electronics-cs",
           "MECH": "mechanical", "BCA": "bca", "MCA": "mca", "ES&H": "humanities-sciences"}
name_dept = {}
for code, folder in rosters.items():
    fp = os.path.join(ROOT, "02-departments", folder, "faculty.md")
    if not os.path.isfile(fp):
        continue
    for nm in re.findall(r"(?:Dr\.|Mr\.|Mrs\.|Ms\.|Cdr\.)\s*([A-Z][a-zA-Z. ]{2,40}?)(?=\s*\|)", read(fp)):
        name_dept[nm.strip()] = code
for r in faculty_rows:
    if r.get("name"):
        # match by last-name token
        for nm, code in name_dept.items():
            if nm.split()[-1] in r["name"] and len(nm.split()[-1]) > 3:
                r["department_code"] = code
                break
json.dump({"faculty": faculty_rows}, open(os.path.join(OUT, "faculty.json"), "w"),
          indent=1, ensure_ascii=False)
print("faculty rows:", len(faculty_rows))

# --------------------------------------------------------------------------
# 7. grids.json — per dept+year time grids
# --------------------------------------------------------------------------
grids = []
def grid(code, year, slots, days, sat):
    grids.append({"department_code": code, "year": year, "working_days": days,
                  "slots": slots, "saturday": sat})

def slot_times(start_hour: int, start_min: int, count: int, duration: int = 60) -> list:
    """A run of `count` contiguous `duration`-minute slots from (start_hour:start_min)."""
    out = []
    for i in range(1, count + 1):
        s = start_hour * 60 + start_min + (i - 1) * duration
        e = s + duration
        out.append({"slot": i, "start": f"{s // 60:02d}:{s % 60:02d}",
                    "end": f"{e // 60:02d}:{e % 60:02d}"})
    return out

# Real SE/TE grid: 9 x 1h, 08:30-17:30 (break at T4 = 11:30-12:30).
se_slots = slot_times(8, 30, 9)
# BE: 8 x 1h, 08:30-16:30, no Saturday.
be_slots = slot_times(8, 30, 8)
# EXTC (even sem 2025-26) starts 09:30.
extc_slots = slot_times(9, 30, 9)
for code in ("COMP", "IT", "EXTC", "E&CS", "MECH", "CIVIL", "AI&ML", "BCA", "MCA", "ES&H"):
    grid(code, 2, se_slots, [0, 1, 2, 3, 4, 5], "IP / co-curricular / notional learning")
    grid(code, 3, se_slots, [0, 1, 2, 3, 4, 5], "IP / PBL / co-curricular / notional learning")
grid("COMP", 4, be_slots, [0, 1, 2, 3, 4], "none (BE has no Saturday block; 5th theory lecture online)")
grid("IT", 4, be_slots, [0, 1, 2, 3, 4], "none (BE has no Saturday block; 5th theory lecture online)")
grid("EXTC", 4, extc_slots, [0, 1, 2, 3, 4, 5], "IP / RBL / co-curricular / notional")
json.dump({"grids": grids}, open(os.path.join(OUT, "grids.json"), "w"), indent=1, ensure_ascii=False)
print("grids:", len(grids))

# --------------------------------------------------------------------------
# 9. calendar.json
# --------------------------------------------------------------------------
calendar = {
    "academic_year": AY,
    "odd_semester": {"start": "2026-06-08", "end": None, "_note": "end = result window 3rd week Nov 2026"},
    "even_semester": {"start": "2027-01-02", "end": None},
    "holidays": ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19"],
    "exam_windows": [
        {"label": "ISE-I", "start": "2026-07-13", "end": "2026-07-15"},
        {"label": "ISE-II", "start": "2026-08-22", "end": "2026-08-25"},
        {"label": "ATKT", "start": "2026-08-03", "end": "2026-08-14"},
    ],
    "ip_pbl_dates": ["2026-08-08", "2026-08-22", "2026-09-12", "2026-09-26", "2026-10-03"],
    "events": {"zephyr": "2026-09-29 to 2026-10-01"},
    "rules": [
        "each faculty: min 42 lectures + 10 practical/tutorial sessions per semester",
        "90 instructional days; holidays compensated in 4th extra slot (first 6 weeks)",
        "Saturday co/extra-curricular count toward AICTE 100 Activity Points",
    ],
}
json.dump(calendar, open(os.path.join(OUT, "calendar.json"), "w"), indent=1, ensure_ascii=False)
print("calendar.json done")
