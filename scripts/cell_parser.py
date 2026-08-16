"""Pure cell-parsing helpers for the TCET source adapter.

``parse_cell`` turns one grid-table entry into a structured cell dict. It is
extracted from ``generate_tcet_import.py`` so the parse rules are unit-testable
without re-running the whole adapter (which regenerates ``info/import/*.json``
on import). Positional parsing rules (Phase 4, DD-044):

- **Lab cells** are ``Lab <SUBJECT> <BATCH> <FACULTY...> <ROOM>``: the faculty
  sit between the batch pattern and the room, so they are parsed by position —
  the old glossary gate systematically dropped the second initial of a pair
  (VK, LJS, RS, HP, MP-as-initial), turning real parallel windows into
  "shared-faculty" windows that can never co-locate.
- **Subject** is the FIRST legend-code token in label order, long forms
  included: "IIS MP 608" is the IIS lecture taught by MP (Megharani Patil),
  not an MP lecture — the initial MP collides with the Microprocessor code.
- **Faculty** in non-lab cells are the initial-like tokens BETWEEN the subject
  token and the room, still gated by the known-initials set so elective
  course names ("ERP"/"IOT"/"Robo") are never mistaken for teachers.
"""
import re

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

    # Lab cells are positional: "Lab <SUBJECT> <BATCH> <FACULTY...> <ROOM>"
    # (e.g. "Lab IIS A1A2 SB/MP 304"). The faculty sit between the batch
    # pattern and the room, so parse them by position — the old glossary gate
    # systematically dropped the second initial of a pair (VK, LJS, RS, HP,
    # MP-as-initial) and mis-took a legend code in the faculty slot (SB/MP ->
    # subject MP). That loss is what turned real parallel windows into
    # "shared-faculty" windows that can never co-locate (DD-036 / DD-044).
    if re.match(r"^\s*Lab\b", e) and bm:
        before = e[: bm.start()].replace("Lab", "", 1).strip()
        cand_subj = before.split()[0] if before.split() else None
        if cand_subj and (cand_subj in legend_codes
                          or cand_subj.split("-")[0] in legend_codes):
            cell["subject"] = cand_subj
            tail = e[bm.end():]
            # cut at the first room number if present
            if rooms:
                ri = tail.find(rooms[0])
                if ri != -1:
                    tail = tail[:ri]
            fac = []
            for chunk in re.split(r"[/\s]+", tail.strip()):
                chunk = chunk.strip()
                if re.fullmatch(r"[A-Za-z]{2,5}", chunk):
                    fac.append(chunk)
            cell["faculty"] = fac
            cell["kind"] = "LAB"
            return cell

    # faculty initials: tokens that appear in legend initials or glossary.
    # Two passes: the short form catches 1-2 uppercase (SuS, PD, NW); the long
    # form catches 3+ uppercase glossary initials (SPS, VNS, HPK) that the
    # short regex silently drops — a real source of duplicate-faculty windows.
    toks = re.findall(r"\b[A-Z][a-z]?[A-Z]?[a-z]?\b", e)
    known = legend_initials | glossary_initials
    fac = [t for t in toks if t in known and len(t) >= 2 and t not in legend_codes]
    if len(fac) <= 1:
        long_toks = re.findall(r"\b[A-Z]{2,4}\b", e)
        extra = [t for t in long_toks if t in known and t not in fac and t not in legend_codes]
        if extra and len(fac) == 0:
            fac = extra
        elif extra and len(fac) == 1:
            fac = fac + [t for t in extra if t != fac[0]]
    if fac:
        cell["faculty"] = fac
    # subject: the FIRST legend-code token in label order, scanning the full
    # token set (long forms included). "IIS MP 608" is the IIS lecture taught
    # by MP (Megharani Patil) — the old short-form scan never saw "IIS" and
    # mis-took the faculty initial MP (also a legend code) as the subject,
    # inflating MP's demand to 6h and dropping IIS's lectures entirely.
    subj_match = None
    all_toks = re.findall(r"\b[A-Za-z][A-Za-z0-9&.\-]{1,13}\b", e)
    for t in all_toks:
        if t in legend_codes:
            cell["subject"] = t
            subj_match = t
            break
    # faculty: initial-like tokens BETWEEN the subject token and the room.
    # Position beats the glossary gate: "IIS MP 608" -> MP, "CSS DS 532" -> DS.
    # Tokens that are not known initials (course names like "ERP"/"IOT" in
    # elective cells) stay excluded, and the subject token itself never
    # counts as its own faculty.
    if subj_match:
        after = e[e.find(subj_match) + len(subj_match):]
        if rooms:
            ri = after.find(rooms[0])
            if ri != -1:
                after = after[:ri]
        stop_words = {"TUT", "TUTORIAL", "NOTIONAL", "ONLINE", "ON-LINE"}
        fac = []
        for chunk in re.split(r"[/\s]+", after.strip()):
            chunk = chunk.strip()
            if not re.fullmatch(r"[A-Za-z]{2,5}", chunk):
                continue
            if chunk.upper() in stop_words or chunk == subj_match:
                continue
            if chunk in known:
                fac.append(chunk)
        if fac:
            cell["faculty"] = fac
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
