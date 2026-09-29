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

    def test_default_grade_is_fourth(self):
        import importlib
        importlib.reload(h)
        try:
            items = h.parse_bbox(GRID.read_text(encoding="utf-8"), today=dt.date(2026, 9, 29))
            self.assertEqual([a["text"] for a in items if a["subject"] == "Math"], ["Finding Factors"])
        finally:
            h.GRADE = None

    def test_override_wrapper_is_accepted(self):
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"deck_sha256": "abc", "assignments": [{"due": "2026-09-30", "text": "Read ch. 3"}]}, f)
        items = h.load_json(f.name, today=TODAY)
        self.assertEqual(items[0]["text"], "Read ch. 3")

    def test_grade_filter(self):
        h.GRADE = "5th"
        items = h.parse_bbox(GRID.read_text(encoding="utf-8"), today=dt.date(2026, 9, 29))
        math = [a for a in items if a["subject"] == "Math"]
        self.assertEqual([a["text"] for a in math], ["Complete ÷ Powers of 10 Mystery Picture"])
        self.assertEqual(len(items), 3)

    def test_merged_header_row_still_splits_into_columns(self):
        # pdfminer sometimes joins several headers into one line
        def word(t, x0, x1, y0=64, y1=80):
            return f'<word xMin="{x0}" yMin="{y0}" xMax="{x1}" yMax="{y1}">{t}</word>'
        xml = f"""<doc><page width="720" height="405"><flow>
          <block xMin="26" yMin="24" xMax="245" yMax="46"><line>{word("Week", 26, 75, 24, 46)}{word("of", 79, 98, 24, 46)}{word("September", 102, 200, 24, 46)}{word("28th", 204, 245, 24, 46)}</line></block>
          <block xMin="40" yMin="64" xMax="560" yMax="80"><line>{word("MONDAY", 40, 100)}{word("9/28", 106, 134)}{word("TUESDAY", 175, 237)}{word("9/29", 243, 271)}{word("WEDNESDAY", 304, 382)}{word("9/30", 388, 414)}</line></block>
          <block xMin="162" yMin="99" xMax="249" yMax="150"><line>{word("Spelling", 162, 220, 99, 116)}</line><line>{word("test", 162, 190, 116, 133)}</line></block>
          <block xMin="320" yMin="99" xMax="400" yMax="120"><line>{word("Read", 320, 360, 99, 116)}{word("ch.", 362, 380, 99, 116)}{word("4", 382, 390, 99, 116)}</line></block>
        </flow></page></doc>"""
        items = h.parse_bbox(xml, today=dt.date(2026, 9, 29))
        self.assertEqual([(a["due"], a["subject"], a["text"]) for a in items], [
            ("2026-09-29", "Spelling", "test"),
            ("2026-09-30", None, "Read ch. 4"),
        ])

    def test_pdf_layout_via_pdfminer(self):
        try:
            import pdf_layout
        except SystemExit:
            self.skipTest("pdfminer.six not installed")
        xml = pdf_layout.convert(str(GRID.parent / "deck-2026-09-28.pdf"))
        items = h.parse_bbox(xml, today=dt.date(2026, 9, 29))
        self.assertEqual([(a["due"], a["subject"], a["text"]) for a in items], [
            ("2026-09-28", "Math", "4th: Finding Factors"),
            ("2026-09-28", "Math", "5th: Complete ÷ Powers of 10 Mystery Picture"),
            ("2026-09-28", "Writing", "Celia Cruz Types of Sentences"),
            ("2026-09-29", "Writing", "Celia Cruz Conjunctions"),
        ])

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
        self.assertEqual(a, b, "output must not depend on when it was generated")


if __name__ == "__main__":
    unittest.main()
