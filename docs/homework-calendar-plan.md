# Homework on the DAKboard calendar — plan

Goal: the teacher's Google Slides deck of homework assignments shows up as
events on the DAKboard calendar, next to the family calendars that are
already imported there, with no manual copying.

Deck: https://docs.google.com/presentation/d/1381vHftL6aBWDcsJ-fN1iB8jrZOLwMlsVW9mPdq-Lpw/edit

## How it fits together

```
Google Slides deck  --(scheduled fetch)-->  parser  -->  homework.ics  -->  GitHub Pages
                                                            (this repo)      https://rramir16.github.io/reading-board/homework.ics
                                                                                        |
                                                                                        v
                                                                DAKboard Calendar block, "Add Calendar URL"
```

DAKboard's Calendar block accepts any public ICS/iCal URL, so the whole job
is to turn the deck into a well-formed `.ics` file and keep it fresh at a
stable public URL. This repo is already published at
`rramir16.github.io/reading-board`, so the ICS can live here beside the
reading tile and the same GitHub Pages deploy serves it.

The "cron job" is a scheduled GitHub Actions workflow in this repo. Nothing
runs at home, nothing needs a server, and if a run fails the last good
`homework.ics` stays in place.

## Pieces

### 1. Fetching the deck

Three ways, in order of preference. Which one applies depends on how the
teacher shared the deck, which is the first thing to check.

| Sharing on the deck                         | How the job reads it                                                                 | Secrets needed                |
| ------------------------------------------- | ------------------------------------------------------------------------------------ | ----------------------------- |
| "Anyone with the link" can view             | Plain HTTPS GET of `.../presentation/d/<id>/export/txt` (no login)                   | none                          |
| Shared only with specific Google accounts   | Google Slides API with an OAuth refresh token for one of those accounts               | client id, client secret, refresh token |
| Restricted to the school's Workspace domain | Same as above, using the student's school account, if the school allows API access; otherwise ask the teacher to loosen sharing or to publish the deck to the web | as above                      |

The `export/txt` path is the simplest and needs no credentials at all. The
Slides API path is more robust (structured slide objects, speaker notes,
tables) and is the fallback if the deck is not link-shareable.

Neither could be tested from this session: the Drive connector attached
here does not have the deck (it returns "not found"), and this sandbox has
no network route to docs.google.com. Step 0 below covers that.

### 2. Parsing assignments

Teacher decks usually follow one of a few shapes:

- one slide per week, titled "Week of September 22", with a bullet per weekday;
- one slide per day, titled with the date;
- one running slide per subject, with "due Friday" style lines.

The parser is a small Python script (`scripts/homework_to_ics.py`) with a
deliberately narrow job:

1. Split the export into slides.
2. Find a date anchor on each slide (a full date, or "Week of ...", or a weekday name resolved against the slide's week).
3. Emit one assignment per bullet: `{ due: YYYY-MM-DD, subject?, text }`.
4. Ignore boilerplate slides (title slide, "reminders", "specials schedule") by a small allow/deny word list that we tune after seeing the deck.

Because the format is unknown until we can read the deck, the parser gets
written against a saved copy of the real export (`fixtures/deck-YYYY-MM-DD.txt`)
and a unit test that pins the expected assignments. When the teacher changes
their layout, the test fails loudly in Actions instead of the board going
quietly stale.

Fallback if the deck turns out to be free-form and hard to parse with rules:
send the slide text to the Claude API with a fixed JSON schema
(`[{due, subject, text}]`) and let the model do the extraction. Costs a
GitHub secret for the API key and a few cents a month. Worth keeping in
the back pocket, not the first choice.

### 3. Writing the ICS

- One all-day `VEVENT` per assignment on its due date. All-day events show
  on DAKboard's calendar without a fake time.
- `SUMMARY`: short and scannable, e.g. `HW: Math p. 42 #1-10`. A prefix
  or emoji lets the eye separate homework from family events.
- `DESCRIPTION`: the full bullet text plus a link back to the deck.
- `UID`: a stable hash of `due + text`, so re-running the job does not
  create duplicates and DAKboard updates in place when wording changes.
- `X-WR-CALNAME: Homework`, `X-WR-TIMEZONE` set to the family's zone.
- Only emit events from, say, two weeks back to the end of the school year,
  so the file stays small.

The `ics` Python package or hand-written lines both work; the format is
simple enough that a 40-line writer with correct line folding and CRLF
endings is fine and avoids a dependency.

### 4. Scheduling and publishing

A Claude Routine (Claude Code on the web) fires a fresh cloud session each
weekday morning. The session fetches the deck, runs the scripts, reads the
slide itself to check the result, and commits `homework.ics` to `main`
when it changed. GitHub Pages then serves it, the same way it serves
`index.html` and the `art/` folder. The exact steps are in
`docs/routine.md`. Nothing runs at home.

The cloud environment's network policy must allow `docs.google.com` and
`*.googleusercontent.com` (the export redirects there). The session installs
`pdfminer.six` from PyPI at the start of each run.

A GitHub Actions workflow did this job while the Routine could not reach
Google; it was removed once the network policy was opened, to avoid two
schedulers writing the same file.

### 5. DAKboard side

Calendar block, Calendar tab, Connected Calendars, "Add Calendar URL",
paste the Pages URL. Give it its own colour. DAKboard re-polls URL
calendars on an interval set by the plan tier, so a change in the deck
shows on the board after: Actions cron delay (up to 2h) + DAKboard poll.
That is fine for homework that is posted days ahead. If it ever needs to
be faster, Phase 2 below moves the events into a real Google Calendar,
which DAKboard refreshes more often through its native integration.

## Phases

**Phase 0, unblock (needs you):**

1. Open the deck's Share dialog and note whether it is "Anyone with the
   link", "Restricted", or domain-limited. If you can, set it to "Anyone
   with the link, Viewer". If not, share it with the Google account that
   is connected to Claude, or one you can create an API token for.
2. Paste the raw text of a typical week's slide (or a screenshot) here so
   the parser can be written against the real layout.
3. Confirm the timezone for the board and the school year end date.

**Phase 1, working pipeline (one session):**

- `scripts/fetch_deck.py`, `scripts/homework_to_ics.py`, fixture + test.
- `.github/workflows/homework.yml` on a 2-hour weekday cron.
- First `homework.ics` committed by hand from the fixture so the DAKboard
  subscription can be set up the same day.

**Phase 2, optional polish:**

- Push events into a dedicated Google Calendar via the Calendar API
  instead of (or in addition to) the ICS file, for faster DAKboard refresh.
- A small "This week's homework" HTML tile, in the same style as the
  reading tile, fed by `homework.json`, for a DAKboard Website block.
- A checklist of done/not-done that Rey can tick, if that turns out to be
  useful.

## Risks and how the plan handles them

- **Deck not readable without login.** Handled by the OAuth path; needs a
  one-time token setup stored as GitHub secrets.
- **Teacher changes slide layout mid-year.** Fixture test fails the
  Actions run; old ICS stays; fix the parser. Consider the Claude API
  extraction fallback if it keeps happening.
- **Duplicate events on DAKboard.** Stable UIDs prevent this.
- **Google rate limits on `export/txt`.** A fetch every 2 hours is far
  below anything Google throttles; add a cache-busting header only if
  stale responses show up.
- **Board shows homework late.** Cron interval plus DAKboard poll; both
  are tunable, and Phase 2 removes most of the DAKboard-side delay.

## Status

Live. The Routine "Homework calendar check" runs weekdays at 6:40am
Eastern. The calendar is at
https://rramir16.github.io/reading-board/homework.ics.

| File | Purpose |
| --- | --- |
| `docs/routine.md` | What the Routine does each run |
| `scripts/fetch_deck.py` | Downloads the public text and PDF exports of the deck |
| `scripts/pdf_layout.py` | Word positions from the PDF (pdfminer), plus a readable per-column dump |
| `scripts/homework_to_ics.py` | Grid parser, JSON input mode, ICS writer; `GRADE`, `TIMEZONE`, `SUMMARY_PREFIX` at the top |
| `tests/` | Parser tests, including a fixture built from the real slide for the week of Sept 28 |
| `homework.ics`, `homework.json` | The published calendar and the assignment list behind it |
