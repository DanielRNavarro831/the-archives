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
FOOTER_MARGIN = 40      # anything this close to the bottom is the copyright/page number
# The two text columns are split at the middle of the page (306 on the letter-size Rules
# Reference; 216 on the smaller Rulebook, whose columns were being merged together before).

# The Rulebook's icon font stores some icons as ordinary ASCII characters instead of the
# private-use characters the other PDFs use. Worked out from the text around each one.
ASCII_ICONS = {chr(cp): name for cp, name in {
    0x01: "boost", 0x02: "evade", 0x03: "cloak", 0x05: "reinforce", 0x06: "coordinate", 0x07: "jam",
    0x08: "slam", 0x0D: "torpedo", 0x0E: "missile", 0x14: "payload", 0x17: "modification",
    0x1A: "turnleft", 0x1B: "bankleft", 0x1C: "straight", 0x1D: "bankright", 0x1E: "turnright",
    0x1F: "stop", 0x21: "sloopleft", 0x22: "kturn", 0x23: "sloopright", 0x24: "trollright",
    0x25: "hit", 0x26: "crit", 0x29: "focus", 0x2A: "lock", 0x2B: "rotate", 0x2C: "reversebankright",
    0x2D: "reversestraight", 0x2E: "reversebankleft", 0x31: "reload", 0x32: "forcepower",
    0x33: "barrelroll", 0x35: "calculate", 0x39: "bullseyearc", 0x3A: "reararc", 0x3B: "frontarc",
    0x3C: "doubleturretarc", 0x3D: "singleturretarc", 0x3E: "charge", 0x3F: "force",
}.items()}


def doubled_icons(doc):
    """True when the PDF writes every icon twice in a row (the Rulebook does: outline + fill)."""
    pairs = total = 0
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    t = "".join(c for c in s["text"] if ord(c) >= 0xE000)
                    if s["font"].startswith("X-WingIcons") and t:
                        total += 1
                        pairs += len(t) % 2 == 0 and all(t[i] == t[i + 1] for i in range(0, len(t), 2))
    return total > 20 and pairs / total > 0.5


def span_text(span, doubled=False):
    out = []
    icon_font = span.get("font", "").startswith("X-WingIcons")
    text = span["text"]
    if doubled and icon_font:
        # "{force}{force}" drawn twice -> one; keeps a real pair like {missile}{missile} drawn twice (4 chars)
        t = [c for c in text if ord(c) >= 0xE000]
        if t and len(t) % 2 == 0 and all(t[i] == t[i + 1] for i in range(0, len(t), 2)):
            seen, keep = 0, []
            for c in text:
                if ord(c) >= 0xE000:
                    seen += 1
                    if seen % 2 == 0:
                        continue
                keep.append(c)
            text = "".join(keep)
    for ch in text:
        cp = ord(ch)
        if icon_font and ch == " " and text == " " and span["bbox"][2] - span["bbox"][0] > 4.5:
            out.append("{trollleft}")   # the Rulebook's left Tallon Roll icon is stored as a (wide) space
        elif icon_font and cp < 0x80 and ch != " ":
            out.append("{" + ASCII_ICONS.get(ch, f"icon-ascii-{cp:02X}") + "}")
        elif 0xF0000 <= cp <= 0x10FFFF or 0xE000 <= cp <= 0xF8FF:
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
    if font.startswith(PART_TITLE_FONT):
        return "h1"
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


PART_TITLE_FONT = "KimberleyBl"   # the Rulebook's big part titles ("SETUP", "SQUAD BUILDING", ...)
PART_TITLES = False                # set per document: only the Rulebook uses them


def keep_span(s):
    if s["font"].startswith(PART_TITLE_FONT):
        return PART_TITLES and s["size"] >= 16 and len(re.sub(r"[^A-Za-z]", "", s["text"])) >= 3
    if not s["font"].startswith(BODY_FONTS):
        return False
    small_caps = "SC70" in s["font"] or "Obliq" in s["font"]
    return s["size"] >= 8.0 or (small_caps and s["size"] >= 5.5)


def extract(path):
    doc = pymupdf.open(path)
    global PART_TITLES
    doubled = doubled_icons(doc)
    PART_TITLES = doubled
    paras = []
    for pno, page in enumerate(doc, start=1):
        COLUMN_SPLIT = page.rect.width / 2
        FOOTER_Y = page.rect.height - FOOTER_MARGIN
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            x0, y0, x1, y1 = b["bbox"]
            if y0 > FOOTER_Y:
                continue
            col = 0 if x0 < COLUMN_SPLIT - 10 else 1
            # Rulebook: an icon and its text on the same line can start a fraction of a point
            # apart, so read anything within 3pt as one line, left to right
            blocks.append((col, round(y0 / 3) if doubled else y0, x0, b))
        # Boxes: "Example of ..." panels and sidebars such as "Critical Damage Markers" (Rulebook
        # pp. 6-14). Their titles are bold Title Case, unlike the ALL CAPS rules headings. A box is
        # read after the two text columns, so it doesn't cut into the body text. It covers its
        # column (or the whole page, if its title crosses the middle) from its title down to the
        # next heading below it.
        def first_span(b):
            return next((sp for ln in b["lines"] for sp in ln["spans"] if sp["text"].strip()), None)
        def is_heading(b):
            f = first_span(b)
            return f is not None and "Bold" in f["font"] and f["size"] >= 9
        def box_title(b):
            t = first_span(b)["text"].strip() if is_heading(b) else ""
            return (first_span(b)["size"] >= 10.5 if t else False) and re.match(r"^[A-Z][a-z]", t) and "{" not in t
        panels = []
        for _, _, _, c in blocks:
            if not doubled or not box_title(c):   # Rulebook layout only
                continue
            cx0, cy0, cx1, _ = c["bbox"]
            left, right = ((0, page.rect.width) if cx0 < COLUMN_SPLIT < cx1
                           else (0, COLUMN_SPLIT) if cx0 < COLUMN_SPLIT else (COLUMN_SPLIT, page.rect.width))
            below = [b["bbox"][1] for _, _, _, b in blocks if is_heading(b) and b is not c
                     and b["bbox"][1] > cy0 + 5 and left <= b["bbox"][0] < right]
            panels.append((c, cy0, min(below, default=page.rect.height), left, right))
        for i, (col, y0, x0, b) in enumerate(blocks):
            for n, (c, top, bottom, left, right) in enumerate(panels):
                if b is c or (top <= b["bbox"][1] < bottom and left <= b["bbox"][0] < right and not is_heading(b)):
                    blocks[i] = (2, (n, b is not c, col, round(b["bbox"][1] / 3)), x0, b)
                    break
        blocks.sort(key=lambda t: (t[0], t[1], t[2]))
        cur = paras[-1] if paras else None
        prev = None  # (col, y1) of the previous kept line
        for col, _, _, b in blocks:
            for line in b["lines"]:
                line = dict(line)
                spans = []
                for sp in line["spans"]:
                    if not keep_span(sp):
                        continue
                    # some PDFs draw each icon twice (outline + fill) at the same spot: keep one
                    if spans and sp["text"] == spans[-1]["text"] and all(
                            abs(a - b) < 1.5 for a, b in zip(sp["bbox"], spans[-1]["bbox"])):
                        continue
                    spans.append(sp)
                line["spans"] = spans
                kind = classify(line)
                if kind is None:
                    continue
                text = "".join(span_text(s, doubled) for s in line["spans"])
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
                marker = re.match(r"^(Q:|A:|•|◊|◊|\d+\.\s|Step \d|[a-e]\.$)", text)
                if kind in ("h1", "h2", "h3"):
                    starts_new = not (tight and cur is not None and cur["kind"] == kind)
                elif marker:
                    starts_new = True
                elif cur is not None and re.fullmatch(r"[a-e]\.", cur["text"]):
                    starts_new = False          # a lettered sub-step ("a.") and its text are separate blocks
                elif tight and cur is not None and cur["kind"] in ("p", "q"):
                    starts_new = False
                elif dangling:
                    starts_new = False
                else:
                    starts_new = True
                prev = (col, ly1)
                if starts_new:
                    cur = {"kind": kind, "text": text, "page": pno, "col": col, "y": round(ly0, 1)}
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
    # the Rulebook draws the range bonus icon as a plain "g" at the start of the next line
    for prev, p in zip(paras, paras[1:]):
        if prev["text"].endswith("range bonus icon:") and p["text"].startswith("g "):
            prev["text"] += " {rangebonus}"
            p["text"] = p["text"][2:]
    if doubled:
        paras = [p for p in paras if not (p["kind"] == "h1" and p["page"] == 1)]   # cover title
        # Rulebook diagram labels that come through as text: a lone icon, or a run of icons
        # and labels with no sentence in it (the "Ship Layout" card diagram)
        paras = [p for p in paras if not (p["kind"] == "p" and (
            re.fullmatch(r"\s*(\{[a-z]+\}\s*)+", p["text"])
            or (len(re.findall(r"\{[a-z]+\}", p["text"])) >= 3 and not re.search(r"[a-z][.!?:]", p["text"]))))]
    # leftovers of figure labels, e.g. "A A A ( ):" from the Rulebook's drawing of an attack header
    return [p for p in paras if p["text"] and not re.fullmatch(r"(?:[A-Z] )+[()\s:]*", p["text"])]


if __name__ == "__main__":
    data = extract(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{len(data)} paragraphs -> {sys.argv[2]}")
