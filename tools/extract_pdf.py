"""
Step 1 of the data pipeline: turn an XWA PDF into an ordered list of
typed paragraphs (JSON). Run:

    python tools/extract_pdf.py <file.pdf> <out.json>

Each paragraph is {"kind": ..., "text": ..., "page": n} where kind is one of
  h1   - big section title (e.g. "FAQ", "APPENDIX: HUGE SHIPS")
  h2   - glossary entry / sub-section heading (e.g. "BOOST (BOOST)")
  h3   - small-caps sub heading inside an entry
  q    - an FAQ question
  p    - body text (bullets keep their leading marker)

Icons from the X-Wing icon font are converted to tokens like {focus}.
"""
import json
import re
import sys

import pymupdf

from icons import icon_token

BODY_FONTS = ("EurostileLTStd", "X-WingIcons", "Eurostile")
FOOTER_Y = 752          # anything below this is the copyright/page number
COLUMN_SPLIT = 306      # x coordinate between the two text columns


def span_text(span):
    out = []
    for ch in span["text"]:
        cp = ord(ch)
        if 0xF0000 <= cp <= 0x10FFFF or 0xE000 <= cp <= 0xF8FF:
            out.append(icon_token(cp))
        elif ch in "￼­":
            continue
        else:
            out.append(ch)
    return "".join(out)


def classify(line):
    spans = [s for s in line["spans"] if s["text"].strip()]
    if not spans:
        return None
    first = spans[0]
    font, size = first["font"], first["size"]
    text = "".join(span_text(s) for s in line["spans"]).strip()
    if "Bold" in font and "SC70" not in font and size >= 13:
        return "h1"
    if "Bold" in font and "SC70" not in font and size >= 10.5:
        return "h2"
    if "SC70" in font and size >= 9.5:
        return "h3"
    if text.startswith("Q:"):
        return "q"
    return "p"


def keep_span(s):
    if not s["font"].startswith(BODY_FONTS):
        return False
    small_caps = "SC70" in s["font"] or "Obliq" in s["font"]
    return s["size"] >= 8.0 or (small_caps and s["size"] >= 5.5)


def extract(path):
    doc = pymupdf.open(path)
    paras = []
    for pno, page in enumerate(doc, start=1):
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            x0, y0, x1, y1 = b["bbox"]
            if y0 > FOOTER_Y:
                continue
            col = 0 if x0 < COLUMN_SPLIT - 10 else 1
            blocks.append((col, y0, x0, b))
        blocks.sort(key=lambda t: (t[0], t[1], t[2]))
        cur = paras[-1] if paras else None
        prev = None  # (col, y1) of the previous kept line
        for col, _, _, b in blocks:
            for line in b["lines"]:
                line = dict(line)
                line["spans"] = [s for s in line["spans"] if keep_span(s)]
                kind = classify(line)
                if kind is None:
                    continue
                text = "".join(span_text(s) for s in line["spans"])
                text = re.sub(r"\s+", " ", text).strip()
                if not text:
                    continue
                ly0, ly1 = line["bbox"][1], line["bbox"][3]
                tight = prev is not None and prev[0] == col and -2 < ly0 - prev[1] < 3.5
                # text that runs on into the next column/page: previous paragraph
                # did not end a sentence and this line is not a new item
                dangling = (cur is not None and prev is not None and not tight
                            and cur["kind"] in ("p", "q")
                            and not re.search(r"[.?!:”\")]$", cur["text"])
                            and kind == "p")
                marker = re.match(r"^(Q:|A:|•|◊|◊|\d+\.\s|Step \d)", text)
                if kind in ("h1", "h2", "h3"):
                    starts_new = not (tight and cur is not None and cur["kind"] == kind)
                elif marker:
                    starts_new = True
                elif tight and cur is not None and cur["kind"] in ("p", "q"):
                    starts_new = False
                elif dangling:
                    starts_new = False
                else:
                    starts_new = True
                prev = (col, ly1)
                if starts_new:
                    cur = {"kind": kind, "text": text, "page": pno}
                    paras.append(cur)
                else:
                    if cur["text"].endswith("-") and not cur["text"].endswith(" -"):
                        cur["text"] += text
                    else:
                        cur["text"] += " " + text
    # tidy
    for p in paras:
        p["text"] = re.sub(r"\s+", " ", p["text"]).strip()
        p["text"] = p["text"].replace("\t", " ")
    return [p for p in paras if p["text"]]


if __name__ == "__main__":
    data = extract(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{len(data)} paragraphs -> {sys.argv[2]}")
