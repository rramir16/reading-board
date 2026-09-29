# Homework Routine runbook

A scheduled Claude session runs this each weekday morning. It is the safety
net for the rule-based parser: the teacher's slide layout may change, and a
person reading the slide will get it right when the parser does not.

## Inputs

- The deck: https://docs.google.com/presentation/d/1381vHftL6aBWDcsJ-fN1iB8jrZOLwMlsVW9mPdq-Lpw/edit
  It is shared as "Anyone with the link". Public exports need no login:
  `.../export/pdf` and `.../export/txt`.
- `deck/deck-layout.txt` and `deck/deck-bbox.html`: the latest snapshot the
  GitHub Actions job committed (it runs every two hours on weekdays). Use
  these when the session cannot reach docs.google.com.
- `homework.json`: what the parser produced from that snapshot.
- Rey is in 4th grade. Lines labelled for another grade ("5th: ...") are
  not hers and must not appear on the calendar.

## Steps

1. `git fetch origin main && git checkout main && git pull`.
2. Get the current slide, preferring a fresh copy:
   ```
   python3 scripts/fetch_deck.py deck.txt deck.pdf \
     && pip install -q pdfminer.six \
     && python3 scripts/pdf_layout.py deck.pdf deck/deck-bbox.html
   ```
   If the fetch fails because the network blocks docs.google.com, fall back
   to the committed `deck/deck-bbox.html` and `deck/deck-layout.txt`, and
   say so in the final summary.
3. Run the parser: `python3 scripts/homework_to_ics.py deck/deck-bbox.html /tmp/hw.ics /tmp/hw.json`.
4. Read the slide yourself (`deck/deck-layout.txt` keeps the columns) and
   compare with `/tmp/hw.json`: every assignment under the right day, the
   subject right, nothing missing, nothing from another grade, no template
   or heading text.
5. If the parser is right and `/tmp/hw.json` matches the committed
   `homework.json`: stop. One-line reply, no commit.
6. If the parser is wrong:
   - write `deck/override.json` as
     `{"deck_sha256": "<sha256sum of deck/deck-bbox.html>", "assignments": [{"due": "YYYY-MM-DD", "subject": "...", "text": "..."}]}`;
   - `python3 scripts/homework_to_ics.py --from-json deck/override.json homework.ics`
     and copy the assignments list to `homework.json`;
   - if the fix is a small parser change, make it, add the current
     `deck/deck-bbox.html` as a fixture with a test, and run
     `python3 -m unittest discover -s tests`;
   - commit and push to `main`. The Actions job honours the override until
     the deck changes.
7. Reply with one line: the number of assignments, the date range, and
   whether an override was needed.

## Never

- Publish an assignment you are unsure of; leave it out and say so.
- Edit `index.html` or anything outside `scripts/`, `tests/`, `deck/`,
  `homework.ics`, `homework.json`.
- Force-push or rewrite history.
