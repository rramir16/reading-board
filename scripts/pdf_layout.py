#!/usr/bin/env python3
"""Write a pdftotext -bbox-layout style file from a PDF, in pure Python.

    python3 scripts/pdf_layout.py deck.pdf deck/deck-bbox.html

The GitHub Actions job uses poppler's pdftotext. A Claude Routine running
in a cloud session has no apt, but can `pip install pdfminer.six`, so this
produces the same XHTML shape (page > block > line > word with xMin/yMin/
xMax/yMax measured from the top-left) for scripts/homework_to_ics.py.
"""
import sys
from xml.sax.saxutils import escape

try:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar, LTTextBox, LTTextLine
except ImportError:
    raise SystemExit("pdfminer.six is not installed: pip install pdfminer.six")


def _words(line, page_h):
    words, cur, box = [], [], None
    for ch in line:
        if isinstance(ch, LTChar) and not ch.get_text().isspace():
            cur.append(ch.get_text())
            x0, y0, x1, y1 = ch.bbox
            box = (x0, y0, x1, y1) if box is None else (
                min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1))
        elif cur:
            words.append(("".join(cur), box))
            cur, box = [], None
    if cur:
        words.append(("".join(cur), box))
    # pdfminer measures from the bottom-left; pdftotext from the top-left
    return [(t, b[0], page_h - b[3], b[2], page_h - b[1]) for t, b in words]


def attrs(x0, y0, x1, y1):
    return f'xMin="{x0:.6f}" yMin="{y0:.6f}" xMax="{x1:.6f}" yMax="{y1:.6f}"'


def convert(pdf_path):
    out = ['<?xml version="1.0"?>',
           '<html xmlns="http://www.w3.org/1999/xhtml"><head><title></title></head><body><doc>']
    laparams = LAParams(line_margin=0.3, char_margin=1.0, boxes_flow=None)
    for page in extract_pages(pdf_path, laparams=laparams):
        ph = page.height
        out.append(f'  <page width="{page.width:.6f}" height="{ph:.6f}">')
        out.append('    <flow>')
        for box in page:
            if not isinstance(box, LTTextBox):
                continue
            lines = []
            for line in box:
                if isinstance(line, LTTextLine):
                    ws = _words(line, ph)
                    if ws:
                        lines.append(ws)
            if not lines:
                continue
            bx0 = min(w[1] for l in lines for w in l); by0 = min(w[2] for l in lines for w in l)
            bx1 = max(w[3] for l in lines for w in l); by1 = max(w[4] for l in lines for w in l)
            out.append(f'      <block {attrs(bx0, by0, bx1, by1)}>')
            for ws in lines:
                lx0, ly0 = min(w[1] for w in ws), min(w[2] for w in ws)
                lx1, ly1 = max(w[3] for w in ws), max(w[4] for w in ws)
                out.append(f'        <line {attrs(lx0, ly0, lx1, ly1)}>')
                for t, x0, y0, x1, y1 in ws:
                    out.append(f'          <word {attrs(x0, y0, x1, y1)}>{escape(t)}</word>')
                out.append('        </line>')
            out.append('      </block>')
        out.append('    </flow>')
        out.append('  </page>')
    out.append('</doc></body></html>')
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(convert(sys.argv[1]))
