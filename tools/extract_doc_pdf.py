"""
Step 1 of the data pipeline for single-column PDFs exported from a word processor
(e.g. the Official XWA Epic Rules beta), where headings are told apart by font size
rather than by the XWA layout fonts that tools/extract_pdf.py expects. Run:

    python tools/extract_doc_pdf.py <file.pdf> <out.json> [--promote "Heading", ...]

Output has the same shape as extract_pdf.py: [{"kind", "text", "page"}, ...] with
  h2 - a rules entry (font size 20 or 16)
  h3 - a sub-heading inside an entry (font size 14 or 12)
  p  - body text; bullets start with "• " (sub-bullets "◊ "), numbered steps keep "1. "
Part titles (size 26, e.g. "Wings") are left out: data/sources.json sections start on
those pages and give each part an intro entry. --promote turns the size-14 sub-headings
under the named heading into entries of their own (e.g. "Additional Rules").
"""
import json
import re
import sys

import pymupdf

ENTRY_SIZES = (20, 16)
SUB_SIZES = (14, 12)
PART_SIZE = 26
FOOTER_Y = 730          # page numbers sit below this
BULLETS = {"●": "• ", "○": "◊ ", "■": "• "}


def clean(t):
    t = t.replace("​", "").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


def main():
    pdf, out = sys.argv[1], sys.argv[2]
    promote = set()
    if "--promote" in sys.argv:
        promote = {s.strip() for s in sys.argv[sys.argv.index("--promote") + 1].split(",")}
    doc = pymupdf.open(pdf)
    paras = []
    cur = None                # paragraph being built
    parent_entry = None       # last entry heading (for --promote)

    def flush():
        nonlocal cur
        if cur and cur["text"].strip():
            cur["text"] = clean(cur["text"])
            paras.append(cur)
        cur = None

    for pno, page in enumerate(doc, start=1):
        first_line_on_page = True
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for line in b["lines"]:
                text = "".join(s["text"] for s in line["spans"])
                x, y = line["bbox"][0], line["bbox"][1]
                if y > FOOTER_Y and re.fullmatch(r"\s*\d+\s*", text):
                    continue                                   # page number
                if not text.strip():
                    if not first_line_on_page:
                        flush()                                # blank line = paragraph break
                    continue
                main_span = max(line["spans"], key=lambda s: len(s["text"].strip()))
                size = round(main_span["size"])
                if size >= PART_SIZE:
                    flush()
                    parent_entry = None
                    first_line_on_page = False
                    continue
                if size in ENTRY_SIZES or size in SUB_SIZES:
                    flush()
                    title = clean(text)
                    if size in ENTRY_SIZES:
                        kind = "h2"
                        parent_entry = title
                    else:
                        kind = "h2" if size == SUB_SIZES[0] and parent_entry in promote else "h3"
                    paras.append({"kind": kind, "text": title, "page": pno})
                    first_line_on_page = False
                    continue
                stripped = text.lstrip()
                marker = stripped[:1]
                starts_item = marker in BULLETS or re.match(r"\d+\.​", stripped)
                if starts_item:
                    flush()
                    body = stripped[1:] if marker in BULLETS else stripped
                    prefix = BULLETS.get(marker, "")
                    cur = {"kind": "p", "text": prefix + body, "page": pno}
                elif cur is None and first_line_on_page and paras and paras[-1]["kind"] == "p" and (
                        x > 100 or stripped[:1].islower()):
                    cur = paras.pop()                          # paragraph continues from the previous page
                    cur["text"] += " " + stripped
                elif cur is None:
                    cur = {"kind": "p", "text": stripped, "page": pno}
                else:
                    cur["text"] += " " + stripped
                first_line_on_page = False
        flush()                                                # a paragraph may continue: rejoined above
    flush()
    with open(out, "w", encoding="utf-8") as f:
        json.dump(paras, f, ensure_ascii=False, indent=1)
    print(f"{len(paras)} paragraphs -> {out}")


if __name__ == "__main__":
    main()
