from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from sqlalchemy.orm import Session
from sqlalchemy import select
from io import BytesIO
import csv
import io
from datetime import date, datetime, timedelta
from app.models.generation import TimetableSlot, TimetableInstance
from app.models.rooms import Room
from app.models.faculty import Faculty
from app.models.groups import StudentGroup
from app.models.subjects import Subject

DAYS = {0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}


def _get_lookup_maps(db: Session, slots: list[TimetableSlot]) -> dict:
    """Fetch all related records in bulk to avoid N+1 queries."""
    room_ids = {s.room_id for s in slots if s.room_id}
    faculty_ids = {s.faculty_id for s in slots if s.faculty_id}
    group_ids = {s.student_group_id for s in slots if s.student_group_id}
    subject_ids = {s.subject_id for s in slots if s.subject_id}

    rooms = {r.id: r for r in db.scalars(
        select(Room).where(Room.id.in_(room_ids))).all()}
    faculty = {f.id: f for f in db.scalars(
        select(Faculty).where(Faculty.id.in_(faculty_ids))).all()}
    groups = {g.id: g for g in db.scalars(
        select(StudentGroup).where(StudentGroup.id.in_(group_ids))).all()}
    subjects = {s.id: s for s in db.scalars(
        select(Subject).where(Subject.id.in_(subject_ids))).all()}

    return {
        "rooms": rooms,
        "faculty": faculty,
        "groups": groups,
        "subjects": subjects
    }


def generate_timetable_pdf(
    instance_id: int,
    db: Session,
    title: str = "Timetable",
    slots: list[TimetableSlot] | None = None,
) -> BytesIO:
    """
    Generates a PDF timetable grid for a given instance.
    Returns a BytesIO buffer ready to be sent as a file response.

    Pass ``slots`` to render a pre-filtered subset (e.g. one faculty's
    schedule); otherwise every slot in the instance is loaded.

    When the slots span several student groups (a whole-department instance),
    one grid per group is rendered instead of a single grid cramming every
    group into every cell — a cell holding dozens of sessions would exceed the
    page frame (ReportLab ``LayoutError``). Per-class grids match the college
    artifact (see ``sample/``).
    """
    if slots is None:
        slots = db.scalars(
            select(TimetableSlot).where(
                TimetableSlot.instance_id == instance_id
            ).order_by(
                TimetableSlot.day_of_week,
                TimetableSlot.slot_number
            )
        ).all()

    if not slots:
        # return empty PDF with message
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        doc.build([Paragraph("No slots found for this instance.", styles["Normal"])])
        buffer.seek(0)
        return buffer

    maps = _get_lookup_maps(db, slots)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1*cm,
        rightMargin=1*cm,
        topMargin=1.5*cm,
        bottomMargin=1*cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=16,
        spaceAfter=12
    )
    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Heading2"],
        alignment=TA_CENTER,
        fontSize=11,
        spaceAfter=8,
        textColor=colors.HexColor("#2E4057"),
    )

    # Build slot-time labels once (shared by every group's grid).
    slot_times = {}
    for slot in slots:
        if slot.slot_number not in slot_times:
            slot_times[slot.slot_number] = (
                f"{slot.start_time.strftime('%H:%M')}"
                f" - {slot.end_time.strftime('%H:%M')}"
            )

    # Group the slots per student group so each grid stays page-sized.
    by_group: dict[int | None, list[TimetableSlot]] = {}
    for slot in slots:
        by_group.setdefault(slot.student_group_id, []).append(slot)

    elements = [Paragraph(title, title_style), Spacer(1, 0.3*cm)]
    for group_id, group_slots in by_group.items():
        group_name = maps["groups"].get(group_id).name if group_id is not None and maps["groups"].get(group_id) else "Ungrouped"
        grid = _build_grid(group_slots, maps, slot_times)
        if grid is None:
            continue
        elements.append(Paragraph(f"Group: {group_name}", subtitle_style))
        elements.append(grid)
        elements.append(Spacer(1, 0.4*cm))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _build_grid(slots, maps, slot_times):
    """One group's slot x day grid as a ReportLab Table (or None if empty)."""
    days_used = sorted(set(s.day_of_week for s in slots if s.day_of_week is not None))
    slot_numbers = sorted(slot_times.keys())
    if not days_used:
        return None

    # slot_grid[slot_number][day] = list of sessions
    slot_grid = {sn: {d: [] for d in days_used} for sn in slot_numbers}
    for slot in slots:
        if slot.day_of_week is not None and slot.slot_number is not None:
            subject = maps["subjects"].get(slot.subject_id)
            faculty = maps["faculty"].get(slot.faculty_id)
            room = maps["rooms"].get(slot.room_id)

            cell_text = []
            if subject:
                cell_text.append(subject.name)
            if slot.batch_number is not None:
                cell_text.append(f"Batch B{slot.batch_number}")
            if faculty:
                cell_text.append(f"Faculty: {faculty.name}")
            if room:
                cell_text.append(f"Room: {room.name}")

            slot_grid[slot.slot_number][slot.day_of_week].append(
                "\n".join(cell_text)
            )

    # header row
    header = ["Slot / Time"] + [DAYS.get(d, f"Day {d}") for d in days_used]
    table_data = [header]

    for sn in slot_numbers:
        time_label = slot_times[sn]
        row = [f"Slot {sn}\n{time_label}"]
        for d in days_used:
            cell_sessions = slot_grid[sn][d]
            cell_content = "\n---\n".join(cell_sessions) if cell_sessions else ""
            row.append(cell_content)
        table_data.append(row)

    col_width = (27*cm) / (len(days_used) + 1)
    col_widths = [col_width] * (len(days_used) + 1)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        # header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E4057")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("ROWBACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F0F0")),
        # time column
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (0, -1), 8),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("VALIGN", (0, 1), (0, -1), "MIDDLE"),
        # content cells
        ("FONTSIZE", (1, 1), (-1, -1), 7),
        ("VALIGN", (1, 1), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (-1, -1), "LEFT"),
        # grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUND", (1, 1), (-1, -1), [
            colors.white, colors.HexColor("#F8F9FA")
        ]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    return table


# ── filtering ────────────────────────────────────────────────

def get_filtered_slots(
    db: Session,
    instance_id: int,
    *,
    group_id: int | None = None,
    faculty_id: int | None = None,
    year: int | None = None,
    department: str | None = None,
) -> list[TimetableSlot]:
    """Return an instance's slots narrowed by any combination of filters.

    ``group_id``/``faculty_id`` filter directly on the slot; ``year`` and
    ``department`` filter on the slot's student group.
    """
    query = select(TimetableSlot).where(TimetableSlot.instance_id == instance_id)
    if group_id is not None:
        query = query.where(TimetableSlot.student_group_id == group_id)
    if faculty_id is not None:
        query = query.where(TimetableSlot.faculty_id == faculty_id)
    if year is not None or department is not None:
        query = query.join(
            StudentGroup, TimetableSlot.student_group_id == StudentGroup.id
        )
        if year is not None:
            query = query.where(StudentGroup.year == year)
        if department is not None:
            query = query.where(StudentGroup.department == department)
    query = query.order_by(TimetableSlot.day_of_week, TimetableSlot.slot_number)
    return db.scalars(query).all()


def describe_filters(
    group_id: int | None = None,
    faculty_id: int | None = None,
    year: int | None = None,
    department: str | None = None,
) -> str:
    """Human-readable filter suffix for titles/filenames (empty if none)."""
    parts = []
    if group_id is not None:
        parts.append(f"group {group_id}")
    if faculty_id is not None:
        parts.append(f"faculty {faculty_id}")
    if year is not None:
        parts.append(f"year {year}")
    if department is not None:
        parts.append(department)
    return ", ".join(parts)


# ── CSV ──────────────────────────────────────────────────────

def generate_timetable_csv(slots: list[TimetableSlot], db: Session) -> BytesIO:
    """Render the given slots as a CSV buffer."""
    maps = _get_lookup_maps(db, slots)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Day", "Slot Number", "Start Time", "End Time",
        "Subject", "Subject Code", "Faculty", "Room",
        "Group", "Batch", "Session Type", "Manual Override",
    ])
    for slot in slots:
        subject = maps["subjects"].get(slot.subject_id)
        faculty = maps["faculty"].get(slot.faculty_id)
        room = maps["rooms"].get(slot.room_id)
        group = maps["groups"].get(slot.student_group_id)
        writer.writerow([
            DAYS.get(slot.day_of_week, slot.day_of_week),
            slot.slot_number,
            slot.start_time.strftime("%H:%M") if slot.start_time else "",
            slot.end_time.strftime("%H:%M") if slot.end_time else "",
            subject.name if subject else "",
            subject.subject_code if subject else "",
            faculty.name if faculty else "",
            room.name if room else "",
            group.name if group else "",
            f"B{slot.batch_number}" if slot.batch_number is not None else "",
            slot.session_type.value if hasattr(slot.session_type, "value") else slot.session_type,
            "Yes" if slot.is_manual_override else "No",
        ])
    return BytesIO(output.getvalue().encode("utf-8"))


# ── iCal (.ics) ──────────────────────────────────────────────

_BYDAY = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU"}


def _ical_escape(text) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _first_weekday_on_or_after(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def generate_timetable_ical(
    slots: list[TimetableSlot],
    db: Session,
    *,
    term_start: date | None = None,
    term_end: date | None = None,
    calendar_name: str = "Timetable",
) -> BytesIO:
    """Render slots as an RFC 5545 .ics file of weekly-recurring events.

    Each recurring ``day_of_week`` slot becomes a weekly ``VEVENT`` anchored to
    the first matching weekday on/after ``term_start`` (default today), with an
    optional ``UNTIL`` from ``term_end``.
    """
    maps = _get_lookup_maps(db, slots)
    term_start = term_start or date.today()
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Timetable Generator//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ical_escape(calendar_name)}",
    ]
    for slot in slots:
        if slot.day_of_week is None or slot.start_time is None or slot.end_time is None:
            continue
        anchor = _first_weekday_on_or_after(term_start, slot.day_of_week)
        dtstart = datetime.combine(anchor, slot.start_time).strftime("%Y%m%dT%H%M%S")
        dtend = datetime.combine(anchor, slot.end_time).strftime("%Y%m%dT%H%M%S")
        rrule = f"FREQ=WEEKLY;BYDAY={_BYDAY[slot.day_of_week]}"
        if term_end is not None:
            rrule += ";UNTIL=" + datetime.combine(
                term_end, slot.end_time
            ).strftime("%Y%m%dT%H%M%S")

        subject = maps["subjects"].get(slot.subject_id)
        faculty = maps["faculty"].get(slot.faculty_id)
        room = maps["rooms"].get(slot.room_id)
        group = maps["groups"].get(slot.student_group_id)

        desc = [f"Faculty: {faculty.name}"] if faculty else []
        if group:
            desc.append(f"Group: {group.name}")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{slot.instance_id}-{slot.id}@timetable-generator",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"RRULE:{rrule}",
            f"SUMMARY:{_ical_escape(subject.name if subject else 'Session')}",
        ]
        if room:
            lines.append(f"LOCATION:{_ical_escape(room.name)}")
        if desc:
            lines.append("DESCRIPTION:" + "\\n".join(_ical_escape(d) for d in desc))
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return BytesIO(("\r\n".join(lines) + "\r\n").encode("utf-8"))