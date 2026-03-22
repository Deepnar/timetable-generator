from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from sqlalchemy.orm import Session
from sqlalchemy import select
from io import BytesIO
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
    title: str = "Timetable"
) -> BytesIO:
    """
    Generates a PDF timetable grid for a given instance.
    Returns a BytesIO buffer ready to be sent as a file response.
    """
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

    # build slot time labels
    slot_times = {}
    for slot in slots:
        if slot.slot_number not in slot_times:
            slot_times[slot.slot_number] = (
                f"{slot.start_time.strftime('%H:%M')}"
                f" - {slot.end_time.strftime('%H:%M')}"
            )

    # get unique days and slot numbers
    days_used = sorted(set(s.day_of_week for s in slots if s.day_of_week is not None))
    slot_numbers = sorted(slot_times.keys())

    # build grid — rows = slots, columns = days
    # slot_grid[slot_number][day] = list of sessions
    slot_grid = {sn: {d: [] for d in days_used} for sn in slot_numbers}
    for slot in slots:
        if slot.day_of_week is not None and slot.slot_number is not None:
            subject = maps["subjects"].get(slot.subject_id)
            faculty = maps["faculty"].get(slot.faculty_id)
            room = maps["rooms"].get(slot.room_id)
            group = maps["groups"].get(slot.student_group_id)

            cell_text = []
            if subject:
                cell_text.append(subject.name)
            if faculty:
                cell_text.append(f"Faculty: {faculty.name}")
            if room:
                cell_text.append(f"Room: {room.name}")
            if group:
                cell_text.append(f"Group: {group.name}")

            slot_grid[slot.slot_number][slot.day_of_week].append(
                "\n".join(cell_text)
            )

    # build table data
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

    # create PDF
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

    elements = [
        Paragraph(title, title_style),
        Spacer(1, 0.3*cm),
        table
    ]
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_faculty_pdf(
    faculty_id: int,
    instance_id: int,
    db: Session
) -> BytesIO:
    """Individual faculty timetable PDF."""
    faculty = db.scalars(
        select(Faculty).where(Faculty.id == faculty_id)
    ).first()

    slots = db.scalars(
        select(TimetableSlot).where(
            TimetableSlot.instance_id == instance_id,
            TimetableSlot.faculty_id == faculty_id
        ).order_by(
            TimetableSlot.day_of_week,
            TimetableSlot.slot_number
        )
    ).all()

    title = f"Timetable — {faculty.name if faculty else 'Faculty'}"
    return generate_timetable_pdf(instance_id, db, title)