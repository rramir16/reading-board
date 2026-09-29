# Homework Routine runbook

A scheduled Claude session runs this each weekday morning. It is the only
thing that updates the homework calendar. It reads the teacher's deck, turns
it into `homework.ics`, and pushes to `main`, where GitHub Pages serves
https://rramir16.github.io/reading-board/homework.ics for DAKboard.

## Inputs

- The deck: https://docs.google.com/presentation/d/1381vHftL6aBWDcsJ-fN1iB8jrZOLwMlsVW9mPdq-Lpw/edit
  It is shared as "Anyone with the link", so the public export needs no
  login. `scripts/fetch_deck.py` downloads it.
- Rey is in 4th grade. Lines labelled for another grade ("5th: ...") are
  not hers and must not appear on the calendar. The parser already drops
  them (`GRADE` in `scripts/homework_to_ics.py`).

## Steps

1. `git fetch origin main && git checkout main && git pull origin main`
2. Fetch and lay out the deck:
   ```
   python3 scripts/fetch_deck.py deck.txt deck.pdf
   pip install -q pdfminer.six
   python3 scripts/pdf_layout.py deck.pdf deck-bbox.html
   python3 scripts/pdf_layout.py deck.pdf --print
   ```
   If the fetch fails, stop and say exactly what failed. Do not commit.
3. Run the parser: `python3 scripts/homework_to_ics.py deck-bbox.html homework.ics homework.json`
4. Read the `--print` dump yourself. Each slide lists its text boxes with
   their horizontal position; the MONDAY..FRIDAY headers give each column's
   position and date. Check the parser's `homework.json` against it: every
   assignment under the right day, the subject right, nothing missing, no
   template or heading text, nothing from another grade.
5. If the parser is wrong, write the correct list yourself to
   `homework.json` as `[{"due": "YYYY-MM-DD", "subject": "...", "text": "..."}]`
   and regenerate with
   `python3 scripts/homework_to_ics.py --from-json homework.json homework.ics`.
   If the cause is a small parser change, make it, add the current
   `deck-bbox.html` as a fixture under `tests/fixtures/` with a test, and run
   `python3 -m unittest discover -s tests`.
6. `git status`. If `homework.ics` or `homework.json` changed, commit and
   push to `main`. The repository owner has authorised this Routine to push
   to `main`. If the push is refused, push to `claude/homework-update` and
   say so. If nothing changed, do not commit.
7. Reply with one line: the number of assignments, the date range, and
   whether you had to correct the parser.

## Never

- Publish an assignment you are unsure of; leave it out and say so.
- Commit `deck.pdf`, `deck.txt`, or `deck-bbox.html` (they are ignored).
- Edit `index.html` or anything outside `scripts/`, `tests/`,
  `homework.ics`, `homework.json`.
- Force-push or rewrite history.
