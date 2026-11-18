"""
Finds the example pictures (diagrams, card images, ship examples) in an XWA PDF,
saves each one as an image, and records where it sits on the page so build_data.py can
put it in the right rule entry.

    python tools/extract_figures.py pdfs/rules-reference-v1.4.6.pdf rr [--preview DIR]

Output: site/figures/<prefix>-p<page>-<n>.webp  and  data/raw/<prefix>-figures.json
A figure is a cluster of pictures, vector art and non-body text that sit close together;
its caption is the small explanatory text inside it.
"""
import json
import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image

from icons import icon_token

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "site" / "figures"
FOOTER_Y = 752
HEADER_Y = 30          # page-title band at the top of some pages
GAP = 10               # pieces closer than this are the same figure
DPI = 150

BODY_FONT = re.compile(r"^EurostileLTStd-(Cn|Demi|Bold|Bold-SC70|BoldCn|Demi-SC70|BoldObliq)$")
ART_FONT = re.compile(r"^(Kimberley|BankGothic|Arial)", re.I)   # fonts used inside card images
MARGIN = 24            # the decorative page frame lives in this band


def in_margin(r, W, H):
    return r[0] < MARGIN or r[2] > W - MARGIN or r[1] < MARGIN


def rect_union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def near(a, b, gap=GAP):
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])


def area(r):
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def page_pieces(page):
    W, H = page.rect.width, page.rect.height
    pieces = []          # (rect, kind)
    for info in page.get_image_info():
        r = tuple(info["bbox"])
        if area(r) > 0.45 * W * H or area(r) < 120:          # page background / specks
            continue
        if r[1] > FOOTER_Y or r[3] < HEADER_Y or in_margin(r, W, H):
            continue
        pieces.append((r, "image"))
    for dr in page.get_drawings():
        r = tuple(dr["rect"])
        w, h = r[2] - r[0], r[3] - r[1]
        if w * h > 0.30 * W * H:                            # page frames / big panels
            continue
        if (w > 0.6 * W and h < 4) or (h > 0.6 * H and w < 4):   # long rules/lines
            continue
        if r[1] > FOOTER_Y or area(r) < 40 or in_margin(r, W, H):
            continue
        if not dr.get("fill") and w > 150 and h > 150:     # outline boxes around text
            continue
        pieces.append((r, "art"))
    captions = []
    for bi, b in enumerate(page.get_text("dict")["blocks"]):
        for line in b.get("lines", []):
            for s in line["spans"]:
                if not s["text"].strip():
                    continue
                r = tuple(s["bbox"])
                if r[1] > FOOTER_Y:
                    continue
                # labels/captions (small text) and text inside card art belong to figures;
                # body text, bullets and inline icons (8pt and up) do not
                art_text = s["size"] < 8.0 or ART_FONT.match(s["font"])
                if art_text and not in_margin(r, W, H):
                    pieces.append((r, "text"))
                    if s["font"].startswith("Eurostile") and 7.0 <= s["size"] < 8.0:
                        captions.append((r, s["text"], bi))
                if s["font"].startswith("X-WingIcons") and 6.0 <= s["size"] < 8.5:
                    captions.append((r, "".join(icon_token(ord(ch)) if ord(ch) > 0xE000 else ch for ch in s["text"]), bi))
    # body text lines: real figures never sit on top of them (shadows/backdrops do)
    body_lines = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            spans = [sp for sp in line["spans"] if sp["text"].strip()]
            if spans and BODY_FONT.match(spans[0]["font"]) and spans[0]["size"] >= 8.0 and len(line_text(line)) > 12 and line["bbox"][2] - line["bbox"][0] >= 170:
                body_lines.append(tuple(line["bbox"]))

    def covers_text(r):
        hit = 0
        for t in body_lines:
            ix = max(0, min(r[2], t[2]) - max(r[0], t[0])) * max(0, min(r[3], t[3]) - max(r[1], t[1]))
            if ix > 0.5 * area(t):
                hit += 1
                if hit >= 1:
                    return True
        return False
    pieces = [(r, k) for r, k in pieces if k == "text" or not covers_text(r)]
    return pieces, captions


def line_text(line):
    return "".join(sp["text"] for sp in line["spans"]).strip()


def cluster(pieces):
    boxes = []
    for r, kind in pieces:
        boxes.append([r, {kind}])
    changed = True
    while changed:
        changed = False
        out = []
        while boxes:
            r, kinds = boxes.pop()
            merged = True
            while merged:
                merged = False
                for other in boxes[:]:
                    if near(r, other[0]):
                        r = rect_union(r, other[0])
                        kinds |= other[1]
                        boxes.remove(other)
                        merged = changed = True
            out.append([r, kinds])
        boxes = out
    # a real figure has a picture or vector art, and is not tiny
    return [r for r, kinds in boxes if (kinds & {"image", "art"}) and (r[2] - r[0]) > 45 and (r[3] - r[1]) > 35]


def body_text_lines(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            spans = [sp for sp in line["spans"] if sp["text"].strip()]
            if spans and BODY_FONT.match(spans[0]["font"]) and spans[0]["size"] >= 8.0 and len(line_text(line)) > 3:
                out.append(tuple(line["bbox"]))
    return out


def trim(r, lines):
    """Pull a figure's top/bottom edge in past body-text lines that only clip its edge."""
    r = list(r)
    for _ in range(40):
        moved = False
        for t in lines:
            ov = min(r[2], t[2]) - max(r[0], t[0])
            if ov <= 0.5 * (t[2] - t[0]):
                continue
            cy = (t[1] + t[3]) / 2
            if not (r[1] <= cy <= r[3]):
                continue
            h = r[3] - r[1]
            if cy - r[1] < 0.3 * h:
                r[1] = t[3] + 1; moved = True
            elif r[3] - cy < 0.3 * h:
                r[3] = t[1] - 1; moved = True
        if not moved:
            break
    return tuple(r)


def caption_for(r, captions):
    """Descriptive captions only (sentences); a picture's labels ("Action Bar") stay in the picture."""
    inside = []
    for cr, text, bi in captions:
        cx, cy = (cr[0] + cr[2]) / 2, (cr[1] + cr[3]) / 2
        if r[0] - 2 <= cx <= r[2] + 2 and r[1] - 2 <= cy <= r[3] + 2:
            inside.append((cy, cr[0], text))
    # group into visual lines (centres within 3pt), then read each line left to right
    rows = []
    for cy, x, text in sorted(inside):
        if rows and abs(rows[-1][0] - cy) < 3:
            rows[-1][1].append((x, text))
        else:
            rows.append([cy, [(x, text)]])
    words = [t for _, row in rows for _, t in sorted(row)]
    t = re.sub(r"\s+", " ", " ".join(words)).strip()
    t = re.sub(r"\s+([.,)\]])", r"\1", t)
    return t if re.search(r"[a-z]\.(\s|$)|\)\.", t) and len(t.split()) >= 4 else ""


def main():
    pdf, prefix = sys.argv[1], sys.argv[2]
    preview = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    pages = None
    if "--pages" in sys.argv:
        a, b = sys.argv[sys.argv.index("--pages") + 1].split("-")
        pages = range(int(a), int(b) + 1)
    doc = pymupdf.open(pdf)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    figures = []
    for pno, page in enumerate(doc, start=1):
        if pages and pno not in pages:
            continue
        pieces, captions = page_pieces(page)
        boxes = sorted((trim(b, body_text_lines(page)) for b in cluster(pieces)),
                       key=lambda r: (0 if r[0] < 296 else 1, r[1]))
        boxes = [b for b in boxes if b[3] - b[1] > 35]
        for i, r in enumerate(boxes, start=1):
            pad = 4
            clip = pymupdf.Rect(max(0, r[0] - pad), max(0, r[1] - pad),
                                min(page.rect.width, r[2] + pad), min(FOOTER_Y, r[3] + pad))
            name = f"{prefix}-p{pno}-{i}.webp"
            pix = page.get_pixmap(dpi=DPI, clip=clip, alpha=False)
            if pix.width < 20 or pix.height < 20:
                continue
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.save(OUT_DIR / name, "WEBP", quality=82, method=6)
            col = 0 if r[0] < 296 else 1
            full = r[0] < 296 and r[2] > 316
            figures.append({"file": name, "page": pno, "bbox": [round(v, 1) for v in r],
                            "col": col, "fullWidth": full, "caption": caption_for(r, captions),
                            "w": pix.width, "h": pix.height})
        if preview:
            pix = page.get_pixmap(dpi=60)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            from PIL import ImageDraw
            d = ImageDraw.Draw(img)
            s = 60 / 72
            for r in boxes:
                d.rectangle([r[0] * s, r[1] * s, r[2] * s, r[3] * s], outline=(255, 0, 0), width=2)
            img.save(Path(preview) / f"{prefix}-p{pno}-boxes.png")
    out = ROOT / "data" / "raw" / f"{prefix}-figures.json"
    out.write_text(json.dumps(figures, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum((OUT_DIR / f["file"]).stat().st_size for f in figures)
    print(f"{len(figures)} figures, {total / 1e6:.1f} MB -> {OUT_DIR}")


if __name__ == "__main__":
    main()
