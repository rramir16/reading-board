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

`.github/workflows/homework.yml`:

- `schedule`: every 2 hours on weekdays during school hours, plus a
  `workflow_dispatch` button for manual runs. GitHub cron is UTC, so the
  hours get written accordingly.
- Steps: checkout, set up Python, fetch deck, run parser, write
  `homework.ics` (and `homework.json` as a by-product), commit and push
  only if the file actually changed.
- `permissions: contents: write` so the workflow can commit.
- A parse failure or an empty result fails the run and leaves the previous
  `homework.ics` untouched. GitHub emails on a failed scheduled run.

GitHub Pages then serves `https://rramir16.github.io/reading-board/homework.ics`
the same way it serves `index.html` and the `art/` folder today.

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

Scaffolded on this branch, waiting on deck access to tune the parser:

| File | Purpose |
| --- | --- |
| `.github/workflows/homework.yml` | Scheduled job (every 2h, weekdays, 8am-8pm ET) that fetches, parses, and commits `homework.ics` when it changed |
| `scripts/fetch_deck.py` | Reads the deck as text: public export URL, or the Slides API when the three `GOOGLE_*` secrets are set |
| `scripts/homework_to_ics.py` | Parser and ICS writer; `TIMEZONE`, `SUMMARY_PREFIX`, and the date window are constants at the top |
| `tests/fixtures/sample-deck.txt` | Stand-in deck text; replace with a real export once the deck is readable |
| `tests/test_parser.py` | Pins the parser's behaviour; runs in the workflow before every fetch |

Once the deck is readable: run the workflow by hand from the Actions tab,
download the `deck-text` artifact, copy it over the fixture, adjust the
parser and tests until the output matches the slides, then add the Pages
URL to DAKboard.

## Alternative: a Claude Routine does the reading

Instead of a rule-based parser that breaks when the teacher changes layout,
a scheduled Claude session reads the deck and produces the assignment list,
and the deterministic script only turns that list into a valid `.ics`.

- **Where it runs:** a Routine in Claude Code on the web, firing a fresh
  cloud session in this repo's environment on a schedule (e.g. weekdays at
  7:10am). No home machine involved. The desktop app's scheduled tasks can
  do the same but only while that computer is awake; use that only if the
  deck can be read solely through a browser you are signed into.
- **How it reads the deck:** the Google Drive connector attached to the
  Routine. The deck must be visible to the Google account connected to
  Claude; today that account cannot see it ("not found").
- **What the session does:** read the deck, write `homework.json` as
  `[{due, subject, text}]`, run
  `python3 scripts/homework_to_ics.py --from-json homework.json homework.ics`,
  run the tests, commit and push to main only if the calendar changed, and
  end with a one-line summary. The script rejects malformed dates or empty
  entries, so a confused run cannot publish a broken calendar.
- **Cost:** one short session per firing. A completion notification can be
  turned on so a failed run is visible.

The GitHub Actions workflow and the Routine are interchangeable back ends
for the same `homework.ics`; keep whichever proves more reliable.
