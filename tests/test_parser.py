import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import homework_to_ics as h  # noqa: E402

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample-deck.txt"
GRID = pathlib.Path(__file__).parent / "fixtures" / "deck-bbox-2026-09-28.html"
TODAY = dt.date(2026, 9, 25)


class GridParserTests(unittest.TestCase):
    """The real deck: a weekly grid exported via pdftotext -bbox-layout."""

    def setUp(self):
        h.GRADE = None
        self.items = h.parse_bbox(GRID.read_text(encoding="utf-8"), today=dt.date(2026, 9, 29))

    def tearDown(self):
        h.GRADE = None

    def test_boxes_land_in_their_day_column(self):
        got = [(a["due"], a["subject"], a["text"]) for a in self.items]
        self.assertEqual(got, [
            ("2026-09-28", "Math", "4th: Finding Factors"),
            ("2026-09-28", "Math", "5th: Complete ÷ Powers of 10 Mystery Picture"),
            ("2026-09-28", "Writing", "Celia Cruz Types of Sentences"),
            ("2026-09-29", "Writing", "Celia Cruz Conjunctions"),
        ])

    def test_template_slide_is_ignored(self):
        texts = [a["text"] for a in self.items]
        self.assertFalse(any("___" in t for t in texts))
        self.assertFalse(any(t.startswith("/") for t in texts))

    def test_grade_filter(self):
        h.GRADE = "5th"
        items = h.parse_bbox(GRID.read_text(encoding="utf-8"), today=dt.date(2026, 9, 29))
        math = [a for a in items if a["subject"] == "Math"]
        self.assertEqual([a["text"] for a in math], ["Complete ÷ Powers of 10 Mystery Picture"])
        self.assertEqual(len(items), 3)

    def test_headers_without_dates_fall_back_to_week_of(self):
        xml = GRID.read_text(encoding="utf-8").replace(">9/28<", ">-<").replace(">9/29<", ">-<")
        items = h.parse_bbox(xml, today=dt.date(2026, 9, 29))
        self.assertEqual({a["due"] for a in items}, {"2026-09-28", "2026-09-29"})


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.items = h.parse_assignments(FIXTURE.read_text(), today=TODAY)
        self.by_day = {}
        for a in self.items:
            self.by_day.setdefault(a["due"], []).append(a)

    def test_week_of_anchors_weekdays(self):
        self.assertEqual([a["text"] for a in self.by_day["2026-09-21"]],
                         ["workbook p. 12 #1-10", "20 minutes, log it"])
        self.assertEqual(self.by_day["2026-09-22"][0]["subject"], "Spelling")

    def test_weekday_with_explicit_date(self):
        self.assertEqual(self.by_day["2026-09-24"][0]["subject"], "Science")

    def test_due_phrase_overrides(self):
        self.assertEqual(self.by_day["2026-10-09"][0]["text"], "Book report due October 9")
        self.assertEqual(self.by_day["2026-09-25"][0]["text"], "Reading log due Friday")

    def test_section_headings_are_not_assignments(self):
        texts = [a["text"] for a in self.items]
        self.assertNotIn("Upcoming", texts)
        self.assertNotIn("Specials Schedule", texts)
        self.assertNotIn("Art", texts)
        self.assertIn("No homework!", texts)

    def test_subject_split(self):
        math = self.by_day["2026-09-21"][0]
        self.assertEqual(math["subject"], "Math")

    def test_year_inference_wraps_school_year(self):
        jan = h.parse_date("January 12", dt.date(2026, 12, 20))
        self.assertEqual(jan, dt.date(2027, 1, 12))

    def test_ics_shape(self):
        ics = h.to_ics(self.items, now=dt.datetime(2026, 9, 25, 12, tzinfo=dt.timezone.utc))
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertEqual(ics.count("BEGIN:VEVENT"), len(self.items))
        self.assertIn("DTSTART;VALUE=DATE:20260921", ics)
        self.assertIn("SUMMARY:HW: Math: workbook p. 12 #1-10", ics)
        self.assertNotIn("\n\n", ics)
        for line in ics.split("\r\n"):
            self.assertLessEqual(len(line.encode()), 75)

    def test_from_json_validates_and_sorts(self):
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([
                {"due": "2026-10-02", "text": "Spelling test"},
                {"due": "2026-09-28", "subject": "Math", "text": "p. 40"},
                {"due": "2020-01-01", "text": "ancient, dropped by the window"},
            ], f)
        items = h.load_json(f.name, today=TODAY)
        self.assertEqual([a["due"] for a in items], ["2026-09-28", "2026-10-02"])
        self.assertIsNone(items[1]["subject"])

    def test_stable_uids(self):
        a = h.to_ics(self.items, now=dt.datetime(2026, 9, 25, tzinfo=dt.timezone.utc))
        b = h.to_ics(self.items, now=dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc))
        uids = lambda s: [l for l in s.split("\r\n") if l.startswith("UID:")]
        self.assertEqual(uids(a), uids(b))


if __name__ == "__main__":
    unittest.main()
