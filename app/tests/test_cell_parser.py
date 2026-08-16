"""Cell parser (Phase 4, DD-044): positional lab/lecture parsing.

The parser's glossary gate systematically dropped the second initial of a
pair ("Lab CG D3D4 SuS/HP" -> [SuS]) and mis-took a faculty initial that
collides with a subject code as the subject ("IIS MP 608" -> subject MP).
Both losses turned real parallel windows into unco-locatable "shared-
faculty" windows and inflated demand. These tests pin the positional rules.
"""
from app.tests.test_runner import suite, test


def _parse(label, codes=("IIS", "MP", "CG", "DBMS", "DS", "CSS", "DWM", "UHV",
                         "PS-II", "MP"),
           initials=("SB", "SP", "MP", "MS", "PM", "VN", "VK", "RB", "LJS",
                     "SuS", "HP", "PD", "PP", "RS", "GJ", "SG", "AD", "TN",
                     "DJ", "HR", "LS", "FS", "VG", "NW", "SM", "NeP", "DJ")):
    from scripts.cell_parser import parse_cell
    return parse_cell(label, set(codes), set(initials), set(initials))


@suite("Phase 4 — Cell parser (DD-044)")
def _phase4_cell_parser(s):
    @test("lab faculty parse positionally between batch and room")
    def t_lab_positional(client):
        c = _parse("Lab IIS A1A2 SB/MP 304")
        assert c["subject"] == "IIS", c
        assert c["batch"] == [1, 2], c
        assert c["faculty"] == ["SB", "MP"], c
        assert c["kind"] == "LAB", c
        assert c["room"] == "304", c

    @test("the second initial of a pair is never dropped")
    def t_lab_pair(client):
        assert _parse("Lab MP A1A2 VN/VK 324")["faculty"] == ["VN", "VK"]
        assert _parse("Lab MP A3A4 RB/LJS 325")["faculty"] == ["RB", "LJS"]
        assert _parse("Lab CG D3D4 SuS/HP 324")["faculty"] == ["SuS", "HP"]
        assert _parse("Lab DBMS B3B4 NW LJS 306")["faculty"] == ["NW", "LJS"]
        assert _parse("Lab PS-II A1A2 MP/NeP 203")["faculty"] == ["MP", "NeP"]

    @test("a single-teacher pair stays single (merged later by the solver)")
    def t_lab_single(client):
        c = _parse("Lab DWM A1A2 SG 324")
        assert c["faculty"] == ["SG"], c
        # an initial absent from the glossary is still captured by position
        assert _parse("Lab CSS A1A2 DS 324")["faculty"] == ["DS"]

    @test("a faculty initial that collides with a subject code is not the subject")
    def t_subject_collision(client):
        # "IIS MP 608" = the IIS lecture taught by MP (Megharani Patil).
        c = _parse("IIS MP 608")
        assert c["subject"] == "IIS", c
        assert c["faculty"] == ["MP"], c
        assert c["kind"] == "LECTURE", c
        # the real MP lecture keeps MP as subject, SG as faculty
        c2 = _parse("MP SG 607")
        assert c2["subject"] == "MP" and c2["faculty"] == ["SG"], c2

    @test("lecture faculty sit between subject and room, gated by known initials")
    def t_lecture_faculty(client):
        assert _parse("DS PP TuT 304")["faculty"] == ["PP"]
        assert _parse("UHV AD 607")["faculty"] == ["AD"]
        assert _parse("DBMS HP 606")["faculty"] == ["HP"]
        # an initial missing from the glossary stays a reported gap
        assert _parse("CSS DS 532")["faculty"] == []

    @test("multi-token subjects still parse via the legend fallback")
    def t_multi_token(client):
        c = _parse("M III GS 606", codes=("M III", "DS", "DBMS"),
                   initials=("GS", "PP"))
        assert c["subject"] == "M III", c
        assert c["faculty"] == ["GS"], c
        assert c["kind"] == "LECTURE", c

    return [t_lab_positional, t_lab_pair, t_lab_single, t_subject_collision,
            t_lecture_faculty, t_multi_token]
