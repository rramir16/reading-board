#!/usr/bin/env python3
"""Fetch the teacher's Google Slides deck as plain text.

Two paths, chosen by what is configured:

  1. No credentials: the deck is shared as "Anyone with the link", so the
     public export URL works without a login.
  2. GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN set:
     refresh an OAuth access token and read the deck through the Slides
     API, then flatten every text box on every slide.

Either way the result is plain text, one form feed between slides, written
to stdout or to the path given as the first argument.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DECK_ID = os.environ.get("DECK_ID", "1381vHftL6aBWDcsJ-fN1iB8jrZOLwMlsVW9mPdq-Lpw")
SLIDE_SEP = "\f"


def fetch_public(deck_id):
    url = f"https://docs.google.com/presentation/d/{deck_id}/export/txt"
    req = urllib.request.Request(url, headers={"User-Agent": "reading-board-homework/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    if b"<html" in body[:2000].lower() or "text/html" in ctype:
        raise SystemExit(
            "Google returned an HTML page instead of the deck text. The deck is "
            "probably not shared as 'Anyone with the link'. Either change the "
            "sharing or configure the OAuth secrets for the API path."
        )
    return body.decode("utf-8-sig")


def fetch_via_api(deck_id, client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=data, timeout=60) as resp:
        token = json.load(resp)["access_token"]

    req = urllib.request.Request(
        f"https://slides.googleapis.com/v1/presentations/{deck_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        deck = json.load(resp)

    slides_text = []
    for slide in deck.get("slides", []):
        lines = []
        for element in slide.get("pageElements", []):
            lines.extend(_element_text(element))
        slides_text.append("\n".join(lines))
    return SLIDE_SEP.join(slides_text)


def _element_text(element):
    """Yield the text lines inside a page element (text boxes, tables, groups)."""
    out = []
    shape = element.get("shape")
    if shape and "text" in shape:
        out.extend(_text_runs(shape["text"]))
    table = element.get("table")
    if table:
        for row in table.get("tableRows", []):
            cells = []
            for cell in row.get("tableCells", []):
                cells.append(" ".join(_text_runs(cell.get("text", {}))))
            out.append(" | ".join(c for c in cells if c))
    group = element.get("elementGroup")
    if group:
        for child in group.get("children", []):
            out.extend(_element_text(child))
    return out


def _text_runs(text):
    paragraph, lines = [], []
    for part in text.get("textElements", []):
        run = part.get("textRun")
        if not run:
            continue
        chunk = run.get("content", "")
        while "\n" in chunk:
            head, chunk = chunk.split("\n", 1)
            paragraph.append(head)
            lines.append("".join(paragraph).strip())
            paragraph = []
        paragraph.append(chunk)
    if "".join(paragraph).strip():
        lines.append("".join(paragraph).strip())
    return [l for l in lines if l]


def main():
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh = os.environ.get("GOOGLE_REFRESH_TOKEN")
    try:
        if cid and secret and refresh:
            text = fetch_via_api(DECK_ID, cid, secret, refresh)
        else:
            text = fetch_public(DECK_ID)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Google returned HTTP {e.code} for the deck: {e.reason}")

    if not text.strip():
        raise SystemExit("The deck came back empty; refusing to overwrite the calendar.")

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
