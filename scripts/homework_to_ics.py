#!/usr/bin/env python3
"""Turn the deck's plain text into homework.ics (and homework.json).

    python3 scripts/homework_to_ics.py deck.txt homework.ics [homework.json]
    python3 scripts/homework_to_ics.py --from-json homework.json homework.ics

The second form skips the parser: something else (a Claude Routine reading
the deck) has already produced the assignment list as JSON, and this only
validates it and writes the calendar.

The parser is intentionally small and is expected to be tuned against a
saved copy of the real deck (see tests/fixtures). The rules it applies:

  * slides are separated by a form feed (what fetch_deck.py emits);
  * a line that is a date, "Week of <date>", or a weekday name sets the
    current due date for the lines that follow;
  * every other non-empty line under a date is one assignment;
  * "Subject: text" splits off the subject; "due <date>" inside a line
    overrides the due date;
  * years are inferred so the date lands closest to today, which keeps a
    school year that spans two calendar years working.
"""
import datetime as dt
import hashlib
import json
import re
import sys

DECK_URL = "https://docs.google.com/presentation/d/1381vHftL6aBWDcsJ-fN1iB8jrZOLwMlsVW9mPdq-Lpw/edit"
TIMEZONE = "America/New_York"          # only labels the calendar; events are all-day
CAL_NAME = "Homework"
SUMMARY_PREFIX = "HW"
PAST_DAYS, FUTURE_DAYS = 14, 220        # window of events kept in the file

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

MONTH_RE = r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
DATE_RE = re.compile(
    rf"(?:{MONTH_RE}\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(?P<year>\d{{4}}))?)"
    r"|(?:(?P<m>\d{1,2})/(?P<d>\d{1,2})(?:/(?P<y>\d{2,4}))?)",
    re.I,
)
WEEKDAY_RE = re.compile(r"^\s*(?P<wd>mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\.?\b", re.I)
WEEK_OF_RE = re.compile(r"\bweek\s+of\b", re.I)
DUE_RE = re.compile(r"\bdue\b[:\s]*(?:on\s+)?(?P<rest>.+)$", re.I)
SUBJECT_RE = re.compile(r"^(?P<subject>[A-Za-z][A-Za-z .&/]{1,24}?)\s*[:\-\u2013\u2014]\s+(?P<text>\S.*)$")
BULLET_RE = re.compile(r"^[\s\u2022\u25cb\u25aa\u25a0\u2023\u2043\-\*\u00b7>]+")
# "Upcoming", "Specials Schedule", "Reminders": a short Title Case label with
# no digits or punctuation is a section heading, not an assignment.
HEADING_RE = re.compile(r"^(?:[A-Z][a-z]+\s?){1,3}$")


def infer_year(month, day, today):
    """Pick the year that puts month/day closest to today."""
    best = None
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            cand = dt.date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((cand - today).days) < abs((best - today).days):
            best = cand
    return best


def parse_date(text, today):
    m = DATE_RE.search(text)
    if not m:
        return None
    if m.group("mon"):
        key = m.group("mon").lower().rstrip(".")
        month = 9 if key.startswith("sep") else MONTHS[key[:3]]
        day = int(m.group("day"))
        year = int(m.group("year")) if m.group("year") else None
    else:
        month, day = int(m.group("m")), int(m.group("d"))
        year = m.group("y")
        year = (int(year) + 2000 if year and len(year) == 2 else int(year)) if year else None
    if year:
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    return infer_year(month, day, today)


def parse_weekday(text):
    m = WEEKDAY_RE.match(text)
    if not m:
        return None
    key = m.group("wd").lower()[:3]
    for i, name in enumerate(WEEKDAYS):
        if name.startswith(key):
            return i
    return None


def split_slides(text):
    if "\f" in text:
        return [s for s in text.split("\f")]
    return re.split(r"\n{3,}", text)


def parse_assignments(text, today=None):
    today = today or dt.date.today()
    assignments = []
    for slide in split_slides(text):
        week_monday = None
        current = None
        for raw in slide.splitlines():
            line = BULLET_RE.sub("", raw).strip()
            if not line:
                continue

            date_in_line = parse_date(line, today)
            weekday = parse_weekday(line)
            heading_only = date_in_line and len(DATE_RE.sub("", WEEK_OF_RE.sub("", line)).strip(" ,:-\u2013")) <= 12

            if WEEK_OF_RE.search(line) and date_in_line:
                week_monday = date_in_line - dt.timedelta(days=date_in_line.weekday())
                current = None
                continue
            if weekday is not None and (heading_only or len(line) <= 14):
                if date_in_line:
                    current = date_in_line
                    week_monday = week_monday or current - dt.timedelta(days=current.weekday())
                else:
                    base = week_monday or (today - dt.timedelta(days=today.weekday()))
                    current = base + dt.timedelta(days=weekday)
                continue
            if heading_only:
                current = date_in_line
                continue
            if HEADING_RE.match(line):
                current = None
                continue

            due = current
            dm = DUE_RE.search(line)
            if dm:
                override = parse_date(dm.group("rest"), today)
                wd = parse_weekday(dm.group("rest"))
                if override:
                    due = override
                elif wd is not None:
                    base = week_monday or (today - dt.timedelta(days=today.weekday()))
                    due = base + dt.timedelta(days=wd)
            if due is None:
                continue

            subject = None
            sm = SUBJECT_RE.match(line)
            body = line
            if sm and not parse_weekday(sm.group("subject")):
                subject, body = sm.group("subject").strip(), sm.group("text").strip()
            assignments.append({"due": due.isoformat(), "subject": subject, "text": body})

    lo, hi = today - dt.timedelta(days=PAST_DAYS), today + dt.timedelta(days=FUTURE_DAYS)
    seen, kept = set(), []
    for a in assignments:
        key = (a["due"], a["subject"], a["text"].lower())
        if key in seen or not (lo <= dt.date.fromisoformat(a["due"]) <= hi):
            continue
        seen.add(key)
        kept.append(a)
    kept.sort(key=lambda a: (a["due"], a["subject"] or "", a["text"]))
    return kept


# ---------------------------------------------------------------- ICS ---

def ics_escape(s):
    return s.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    out, enc = [], line.encode("utf-8")
    while len(enc) > 75:
        cut = 75
        while cut > 0 and (enc[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(enc[:cut].decode("utf-8"))
        enc = b" " + enc[cut:]
    out.append(enc.decode("utf-8"))
    return "\r\n".join(out)


def to_ics(assignments, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//reading-board//homework//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CAL_NAME}", f"X-WR-TIMEZONE:{TIMEZONE}",
    ]
    for a in assignments:
        due = dt.date.fromisoformat(a["due"])
        uid = hashlib.sha1(f"{a['due']}|{a['subject']}|{a['text']}".encode()).hexdigest()[:20]
        summary = f"{SUMMARY_PREFIX}: " + (f"{a['subject']}: " if a["subject"] else "") + a["text"]
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@reading-board",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{due:%Y%m%d}",
            f"DTEND;VALUE=DATE:{due + dt.timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{ics_escape(summary)}",
            f"DESCRIPTION:{ics_escape(a['text'] + chr(10) + DECK_URL)}",
            f"URL:{DECK_URL}",
            "CATEGORIES:Homework",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def load_json(path, today=None):
    """Validate a hand-made assignment list: [{due, subject?, text}]."""
    today = today or dt.date.today()
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise SystemExit("homework JSON must be a list of {due, subject, text}")
    out = []
    for i, a in enumerate(raw):
        try:
            due = dt.date.fromisoformat(str(a["due"]))
            text = str(a["text"]).strip()
        except (KeyError, TypeError, ValueError) as e:
            raise SystemExit(f"entry {i} is malformed ({e}): {a!r}")
        if not text:
            raise SystemExit(f"entry {i} has empty text: {a!r}")
        subject = (a.get("subject") or None) and str(a["subject"]).strip()
        out.append({"due": due.isoformat(), "subject": subject or None, "text": text})
    lo, hi = today - dt.timedelta(days=PAST_DAYS), today + dt.timedelta(days=FUTURE_DAYS)
    out = [a for a in out if lo <= dt.date.fromisoformat(a["due"]) <= hi]
    out.sort(key=lambda a: (a["due"], a["subject"] or "", a["text"]))
    return out


def main(argv):
    if len(argv) >= 4 and argv[1] == "--from-json":
        assignments = load_json(argv[2])
        argv = [argv[0], argv[2], argv[3]]
    elif len(argv) >= 3:
        with open(argv[1], encoding="utf-8") as f:
            assignments = parse_assignments(f.read())
    else:
        raise SystemExit(__doc__)
    if not assignments:
        raise SystemExit("No assignments parsed from the deck; leaving the old calendar in place.")
    with open(argv[2], "w", encoding="utf-8", newline="") as f:
        f.write(to_ics(assignments))
    if len(argv) > 3:
        with open(argv[3], "w", encoding="utf-8") as f:
            json.dump(assignments, f, indent=2)
    print(f"{len(assignments)} assignments, {assignments[0]['due']} .. {assignments[-1]['due']}")


if __name__ == "__main__":
    main(sys.argv)
