"""
Step 2 of the data pipeline: turn the extracted paragraphs into the
database the website reads (site/data/archives.js).

    python tools/build_data.py

Inputs
  data/raw/*.json            output of extract_pdf.py
  data/sources.json          which PDF is which version, and page sections
  data/cards-curated.json    hand-maintained card list + aliases + extra rulings
Output
  site/data/archives.js      window.ARCHIVES = {...}
"""
import json
import re
import unicodedata
from pathlib import Path

import compendium
import forum_rulings
import yasb_cards

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "site" / "data" / "archives.js"

FACTIONS = {
    "rebel": "Rebel Alliance", "rebels": "Rebel Alliance",
    "imperial": "Galactic Empire", "empire": "Galactic Empire",
    "scum": "Scum and Villainy", "resistance": "Resistance",
    "first order": "First Order", "republic": "Galactic Republic",
    "separatist": "Separatist Alliance", "separatists": "Separatist Alliance",
}
SLOT_NAMES = {
    "talent": "Talent", "sensor": "Sensor", "cannon": "Cannon", "turret": "Turret",
    "torpedo": "Torpedo", "missile": "Missile", "hardpoint": "Hardpoint",
    "crew": "Crew", "team": "Team", "astromech": "Astromech", "cargo": "Cargo",
    "payload": "Payload", "command": "Command", "illicit": "Illicit",
    "modification": "Modification", "title": "Title", "tech": "Tech",
    "configuration": "Configuration", "forcepower": "Force Power",
    "gunner": "Gunner", "tacticalrelay": "Tactical Relay", "hyperdrive": "Hyperdrive",
}
SLOT_BY_WORD = {v.lower(): k for k, v in SLOT_NAMES.items()}


def slug(s):
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r"\{[^}]+\}", lambda m: m.group(0)[1:-1], s)
    s = s.lower().replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def strip_icons(s):
    return re.sub(r"\s*\(?\{[^}]+\}(\s*(AND|,)\s*\{[^}]+\})*\)?", "", s).strip()


def title_case(s):
    small = {"and", "of", "the", "a", "an", "to", "in", "on", "or", "by", "from", "with", "at"}
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        if i and w in small:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    t = " ".join(out)
    # keep a few things uppercase
    t = re.sub(r"\b(Id|Faq|Tie|Yt|Swx)\b", lambda m: m.group(0).upper(), t)
    return t


def load(name):
    return json.loads((RAW / f"{name}.json").read_text(encoding="utf-8"))


NOISE = re.compile(r"^(VERSION \d[\d.]*|\d{1,2})$")


def section_for(page, sections):
    for s in sections:
        if s["from"] <= page <= s["to"]:
            return s
    return None


# ---------------------------------------------------------------- rules
def build_rules(paras, source, sections, rules, used_ids):
    cur = None
    intro_title = {s["id"]: s.get("introTitle") for s in sections}
    last_section = None
    anchors = []          # (page, col, y) of every heading/paragraph, for placing figures
    for p in paras:
        sec = section_for(p["page"], sections)
        if not sec or sec["kind"] != "rules" or NOISE.match(p["text"]):
            continue
        if sec["id"] != last_section:
            last_section = sec["id"]
            cur = None
            if intro_title.get(sec["id"]):
                cur = new_rule(intro_title[sec["id"]], [], sec, source, p["page"], rules, used_ids)
        if p["kind"] in ("h1", "h2"):
            raw = p["text"]
            icons = re.findall(r"\{[a-z0-9-]+\}", raw)
            name = strip_icons(raw).rstrip(".")
            if name.isupper() or name == name.upper():
                name = title_case(name)
            cur = new_rule(name, icons, sec, source, p["page"], rules, used_ids)
            anchors.append(((p["page"], p.get("col", 0), p.get("y", 0)), cur, -1))
            continue
        if cur is None:
            cur = new_rule(sec["title"], [], sec, source, p["page"], rules, used_ids)
        kind = "h3" if p["kind"] == "h3" else ("q" if p["kind"] == "q" else "p")
        cur["blocks"].append({"k": kind, "t": p["text"]})
        anchors.append(((p["page"], p.get("col", 0), p.get("y", 0)), cur, len(cur["blocks"]) - 1))
    place_figures(source, sections, anchors)
    for r in rules:
        r["blocks"] = [b for b in r["blocks"] if not b.get("_drop")]
    # drop empty entries (headings that were only artwork labels)
    return [r for r in rules if r["blocks"]]


def place_figures(source, sections, anchors):
    """Put each example picture (from tools/extract_figures.py) right after the paragraph
    that comes before it on the page, in reading order (page, column, top to bottom)."""
    path = RAW / f"{source['id']}-figures.json"
    if not path.exists() or not anchors:
        return
    figures = json.loads(path.read_text(encoding="utf-8"))
    cur_path = ROOT / "data" / "figures-curated.json"
    override = json.loads(cur_path.read_text(encoding="utf-8")).get("placeFigure", {}) if cur_path.exists() else {}
    anchors = sorted(anchors, key=lambda a: a[0])
    by_rule_id = {}
    for a in anchors:
        by_rule_id.setdefault(a[1]["id"], a[1])
    inserts = {}
    for f in figures:
        sec = section_for(f["page"], sections)
        if not sec or sec["kind"] != "rules":
            continue
        x0, y0, x1, y1 = f["bbox"]
        if f["file"] in override:
            rule = by_rule_id.get(override[f["file"]])
            if rule:
                inserts.setdefault(id(rule), (rule, []))[1].append((len(rule["blocks"]) - 1, {
                    "k": "fig", "src": "figures/" + f["file"], "cap": f["caption"], "w": f["w"], "h": f["h"],
                    "page": f["page"]}))
            continue
        col = 0 if f["fullWidth"] else f["col"]
        key = (f["page"], col, (y0 + y1) / 2)
        # a heading printed inside the picture is the picture's own title
        inside = [a for a in anchors if a[0][0] == f["page"] and a[2] == -1
                  and (f["fullWidth"] or a[0][1] == col) and y0 - 2 <= a[0][2] <= y1]
        before = inside[:1] or [a for a in anchors if a[0] <= key]
        if not before:
            continue
        _, rule, idx = before[-1]
        inserts.setdefault(id(rule), (rule, []))[1].append((idx, {
            "k": "fig", "src": "figures/" + f["file"], "cap": f["caption"], "w": f["w"], "h": f["h"],
            "page": f["page"]}))
    # short paragraphs printed inside a picture (its labels) are shown by the picture itself
    for (page, col, y), rule, idx in anchors:
        if idx < 0:
            continue
        b = rule["blocks"][idx]
        # only picture titles ("Deploy Example Dropping Bomb") or lines that are nothing but icons
        title_like = "Example" in b["t"] and not b["t"].rstrip().endswith(".") and len(b["t"]) <= 60
        icons_only = not re.sub(r"\{[a-z-]+\}|\s", "", b["t"])
        if b["k"] != "p" or not (title_like or icons_only):
            continue
        for f in figures:
            fx0, fy0, fx1, fy1 = f["bbox"]
            if f["page"] == page and (f["fullWidth"] or f["col"] == col) and fy0 <= y <= fy1:
                b["_drop"] = True
                break
    for rule, items in inserts.values():
        # insert from the end so earlier positions stay valid; keep figure order stable
        numbered = [(idx, n, block) for n, (idx, block) in enumerate(items)]
        for idx, _, block in sorted(numbered, key=lambda t: (t[0], t[1]), reverse=True):
            rule["blocks"].insert(idx + 1, block)


def new_rule(name, icons, sec, source, page, rules, used_ids):
    rid = slug(name)
    if rid in used_ids:
        rid = f"{sec['id']}-{rid}"
    n = 2
    base = rid
    while rid in used_ids:
        rid = f"{base}-{n}"
        n += 1
    used_ids.add(rid)
    r = {"id": rid, "title": name, "icons": icons, "section": sec["title"],
         "sectionId": sec["id"], "source": source["id"], "page": page, "blocks": []}
    rules.append(r)
    return r


# ---------------------------------------------------------------- FAQ
def build_rulings(paras, source, sections, rulings):
    topic = None
    cur = None
    for p in paras:
        sec = section_for(p["page"], sections)
        if not sec or sec["kind"] != "faq" or NOISE.match(p["text"]):
            continue
        t = p["text"]
        if p["kind"] in ("h1", "h2"):
            topic = title_case(strip_icons(t)) if t.isupper() else t
            cur = None
            continue
        if p["kind"] == "q" or t.startswith("Q:"):
            cur = {"id": f"{source['id']}-{len(rulings) + 1}", "source": source["id"],
                   "section": sec["title"], "topic": topic or sec["title"],
                   "page": p["page"], "q": re.sub(r"^Q:\s*", "", t), "a": []}
            rulings.append(cur)
            continue
        if cur is None:
            continue
        cur["a"].append(re.sub(r"^A:\s*", "", t))
    for r in rulings:
        r["a"] = [a for a in r["a"] if a]


# ---------------------------------------------------------------- errata
def build_errata(paras, source, sections, errata):
    category = None
    group = None
    cur = None
    for p in paras:
        sec = section_for(p["page"], sections)
        if not sec or sec["kind"] != "errata" or NOISE.match(p["text"]):
            continue
        t = p["text"].lstrip(".")
        if t.startswith("These products were released"):
            group = "Saw's Renegades and TIE Reaper corrections"
            continue
        if t.startswith("This section contains the official errata"):
            group = "Errata"
            continue
        if p["kind"] in ("h1", "h2"):
            category = title_case(t)
            cur = None
            continue
        if category in ("Insert Sheets", "Dials"):
            # not tied to a single card: keep as a rule-ish errata note
            if cur and cur.get("category") == category and not cur["names"]:
                cur["text"].append(t)
            else:
                cur = {"category": category, "group": group, "names": [], "qualifier": None,
                       "text": [t], "note": None, "page": p["page"], "source": source["id"]}
                errata.append(cur)
            continue
        if t.startswith("(") and cur is not None and cur["note"] is None:
            cur["note"] = t.strip("()").strip()
            continue
        m = re.match(r"^(?P<head>•?(?P<n>.+?)) (?P<rest>(?P=n) should .*)$", t) or re.match(r"^(?P<head>[•\"“A-Z0-9].*?)\s+(?P<rest>(?:Ship ability should|Pilot ability should|"
                     r"Second section|The first sentence|The ability text|Initiative should|"
                     r"Agility reduced|Changed the|Should|[A-Z][\w ]+ should have).*)$", t)
        if m and (cur is None or cur["note"] is not None or not cur["text"]):
            head, rest = m.group("head"), m.group("rest")
            qual = None
            qm = re.search(r"\(([^)]+)\)(?:\s*-\s*(.+))?$", head)
            if re.search(r"\((Closed|Open|Erratic)\)$", head):
                qm = None
            if qm:
                qual = qm.group(1) + (f" — {qm.group(2)}" if qm.group(2) else "")
                head = head[:qm.start()].strip()
            names = [n.strip(" ,") for n in re.split(r",\s*(?:and\s+)?|\s+and\s+(?=•)", head) if n.strip(" ,")]
            names = [re.sub(r"(\S)\(", r"\1 (", n) for n in names]
            cur = {"category": category, "group": group, "names": names, "qualifier": qual,
                   "text": [rest], "note": None, "page": p["page"], "source": source["id"]}
            errata.append(cur)
        elif cur is not None and cur["note"] is None:
            cur["text"].append(t)
        elif t.strip() and cur is not None:
            # a name line on its own (e.g. "Proton Torpedoes") followed by its text
            cur = {"category": category, "group": group, "names": [t.strip()], "qualifier": None,
                   "text": [], "note": None, "page": p["page"], "source": source["id"]}
            errata.append(cur)
        else:
            cur = {"category": category, "group": group, "names": [t.strip()], "qualifier": None,
                   "text": [], "note": None, "page": p["page"], "source": source["id"]}
            errata.append(cur)
    for i, e in enumerate(errata, 1):
        e["id"] = f"errata-{i}"


# ---------------------------------------------------------------- cards
MENTION = re.compile(
    r"(?P<name>(?:(?:[A-Z0-9][\w’'\-\.]*|[“\"][^”\"]+[”\"]|of|the|de|ai)\s){0,4}"
    r"(?:[A-Z0-9][\w’'\-\.]*|[“\"][^”\"]+[”\"]))(?:’s|'s)?\s*[\[(](?P<qual>[^\])]{1,60})[\])]")
NOT_A_NAME = {"If", "When", "While", "After", "Before", "Does", "Can", "Is", "A", "The", "Q", "Note",
              "Step", "Yes.", "No.", "Yes", "No", "For", "This", "That", "Each", "Then", "And", "But",
              "As", "In", "At", "Do", "the", "Unlike", "of", "How", "What"}
ERRATA_TYPES = {"Ship Cards": "Pilot", "Upgrade Cards": "Upgrade", "Condition Cards": "Condition",
                "Standard Loadout Cards": "Standard Loadout", "Remote Cards": "Remote"}


def norm_quotes(s):
    return s.replace("“", "\"").replace("”", "\"").replace("’", "'")


def clean_name(n):
    words = n.split()
    while words and words[0] in NOT_A_NAME:
        words = words[1:]
    n = norm_quotes(" ".join(words)).strip()
    return re.sub(r"'s$", "", n)


def find_mentions(text):
    out = []
    for m in MENTION.finditer(text):
        name = clean_name(m.group("name"))
        qual = m.group("qual").strip()
        # skip quoted rules phrases ("loses a shield" [or ...]) and asides like (see Attack)
        if name.startswith("\"") and name[1:2].islower():
            continue
        if re.match(r"(e\.g\.|i\.e\.|see |or |and |such as|which|negative|that )", qual):
            continue
        if name and len(name) >= 3:
            out.append((name, qual))
    return out


def parse_qualifier(qual, cur):
    """'Rebel, {gunner}' / 'Scum, BTL-A4 Y-wing' -> factions, slot, ship, type."""
    out = {"factions": [], "slot": None, "ship": None, "type": None, "loadout": None}
    if not qual:
        return out
    if " — " in qual:
        qual, out["loadout"] = qual.split(" — ", 1)
    slots = re.findall(r"\{([a-z]+)\}", qual)
    rest = re.sub(r"\{[a-z]+\}", ",", qual)
    for part in re.split(r",|\band\b", rest):
        w = part.strip()
        if not w:
            continue
        lw = w.lower()
        if lw in FACTIONS:
            out["factions"].append(FACTIONS[lw])
        elif lw in SLOT_BY_WORD:
            slots.append(SLOT_BY_WORD[lw])
        elif lw == "pilot":
            out["type"] = "Pilot"
        elif lw == "damage card":
            out["type"] = "Damage Card"
        else:
            out["ship"] = cur.get("shipAliases", {}).get(w, w)
    if slots:
        out["slot"] = [SLOT_NAMES[s] for s in dict.fromkeys(slots) if s in SLOT_NAMES]
        out["type"] = "Upgrade"
    elif out["ship"] and not out["type"]:
        out["type"] = "Pilot"
    return out


def card_id(name, info):
    base = slug(name.replace("•", ""))
    if info.get("ship"):
        return f"{base}-{slug(info['ship'])}"
    if info.get("slot"):
        return f"{base}-{slug(info['slot'][0])}"
    return base


def add_card(cards, cid, name, info, source):
    name = name.replace("•", "").strip()
    c = cards.get(cid)
    if c is None:
        c = cards[cid] = {"id": cid, "name": name, "type": info.get("type") or "Card",
                          "ship": info.get("ship"), "slot": info.get("slot"),
                          "factions": [], "loadout": info.get("loadout"),
                          "text": None, "aliases": [], "rulings": [], "errata": [],
                          "origin": source}
    for f in info.get("factions") or []:
        if f not in c["factions"]:
            c["factions"].append(f)
    for k in ("ship", "slot", "loadout"):
        if not c.get(k) and info.get(k):
            c[k] = info[k]
    if c["type"] == "Card" and info.get("type"):
        c["type"] = info["type"]
    return c


def as_list(v):
    return v if isinstance(v, list) else [v]


def load_playtest(cards):
    """Read data/playtest.json -> {"cards": [...], "rulings": [...]}, with 'base' cards filled in."""
    path = ROOT / "data" / "playtest.json"
    if not path.exists():
        return {"cards": [], "rulings": []}
    src = json.loads(path.read_text(encoding="utf-8"))
    out_cards = []
    for c in src.get("cards", []):
        card = {}
        base = c.get("base")
        if base:
            if base not in cards:
                print(f"WARNING: playtest card {c['id']} uses unknown base card {base}")
            else:
                b = cards[base]
                card = {k: b[k] for k in ("ship", "factions", "stats", "actions", "dial", "shipAbility") if k in b}  # ship-level only
        for k, v in c.items():
            if k not in ("base", "_comment"):
                card[k] = v
        card = {k: v for k, v in card.items() if v is not None}
        card.setdefault("factions", [])
        card.update(rulings=[], errata=[], origin="playtest")
        out_cards.append(card)
    known = {c["id"] for c in out_cards} | set(cards)
    out_rulings = []
    for r in src.get("rulings", []):
        bad = [i for i in r.get("cards", []) if i not in known]
        if bad:
            print(f"WARNING: playtest ruling {r['id']} names unknown cards {bad}")
        out_rulings.append(dict(r, source="playtest", section="Playtest", topic=r.get("topic", "Playtest"),
                                cards=[i for i in r.get("cards", []) if i in known]))
    print(f"Playtest: {len(out_cards)} cards, {len(out_rulings)} rulings "
          f"({sum(1 for x in out_cards + out_rulings if x.get('sample'))} samples)")
    return {"cards": out_cards, "rulings": out_rulings}


def main():
    sources = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
    cur = json.loads((ROOT / "data" / "cards-curated.json").read_text(encoding="utf-8"))

    rules, rulings, errata = [], [], []
    used = set()
    # Epic / huge-ship content can be hidden until the Epic format is finalized
    epic = sources.get("epic", {}) if sources.get("hideEpic") else {}
    epic_sections = set(epic.get("sections", []))
    for src in sources["documents"]:
        src["sections"] = [s for s in src["sections"] if s["id"] not in epic_sections]
    for src in sources["documents"]:
        paras = load(src["raw"])
        # drop leftovers of artwork labels such as "A T c A T c:"
        paras = [p for p in paras
                 if not (len(p["text"]) < 30 and all(len(w) <= 2 for w in p["text"].rstrip(":").split()))]
        rules = build_rules(paras, src, src["sections"], rules, used)
        build_rulings(paras, src, src["sections"], rulings)
        build_errata(paras, src, src["sections"], errata)
    if epic:
        before = len(errata)
        errata = [e for e in errata
                  if e["category"] not in epic.get("errataCategories", [])
                  and not any(n.lstrip("•") in epic.get("errataNames", []) for n in e["names"])]
        print(f"hideEpic: hiding huge-ship sections {sorted(epic_sections)}, "
              f"{before - len(errata)} errata, forum threads {epic.get('forumThreads', [])}")

    cards = {}
    ignore = {norm_quotes(k).lower() for k in cur.get("ignore", [])}
    overrides = {norm_quotes(k).lower(): v for k, v in cur.get("mentionIds", {}).items()}
    unmatched = {}

    # 1. curated cards (names, types, aliases, plain-text matching)
    for c in cur.get("cards", []):
        info = {k: c.get(k) for k in ("type", "ship", "slot", "loadout")}
        info["factions"] = c.get("factions", [])
        cc = add_card(cards, c["id"], c["name"], info, "curated")
        cc["aliases"] = c.get("aliases", [])
        cc["_plain"] = c.get("plain", True)
        cc["text"] = c.get("text")

    # 2. errata entries create / attach cards
    for e in errata:
        e["cards"] = []
        for n in e["names"]:
            clean = norm_quotes(n.replace("•", "")).strip()
            key = (clean + (f" [{e['qualifier']}]" if e["qualifier"] else "")).lower()
            if key in ignore:
                continue
            ids = overrides.get(key) or overrides.get(clean.lower())
            if ids:
                ids = as_list(ids)
                for i in ids:
                    if i not in cards:
                        add_card(cards, i, clean, {"type": ERRATA_TYPES.get(e["category"])}, "errata")
            else:
                info = parse_qualifier(e["qualifier"], cur)
                info["type"] = ERRATA_TYPES.get(e["category"], info["type"])
                slot = cur.get("errataSlots", {}).get(clean)
                if slot and not info.get("slot"):
                    info["slot"] = [slot]
                cid = card_id(clean, info)
                add_card(cards, cid, clean, info, "errata")
                ids = [cid]
            e["cards"].extend(ids)
            for i in ids:
                if e["id"] not in cards[i]["errata"]:
                    cards[i]["errata"].append(e["id"])

    # 3. bracketed mentions inside rulings: Name [Faction, Ship] / Name ({crew})
    ruling_ids = {}
    for r in rulings:
        text = r["q"] + " " + " ".join(r["a"])
        ids = set()
        for name, qual in find_mentions(text):
            key = norm_quotes(f"{name} [{qual}]").lower()
            if key in ignore or name.lower() in ignore:
                continue
            if key in overrides:
                ids.update(as_list(overrides[key]))
                continue
            info = parse_qualifier(qual, cur)
            if not info["type"]:
                unmatched.setdefault(f"{name} [{qual}]", []).append(r["id"])
                continue
            cid = card_id(name, info)
            add_card(cards, cid, name, info, "ruling")
            ids.add(cid)
        ruling_ids[r["id"]] = ids

    # 4. plain-text mentions of distinctive card names
    by_name = {}
    for c in cards.values():
        for a in [c["name"]] + c.get("aliases", []):
            by_name.setdefault(a, set()).add(c["id"])
    for r in rulings:
        text = norm_quotes(r["q"] + " " + " ".join(r["a"]))
        ids = ruling_ids[r["id"]]
        linked_names = {cards[i]["name"] for i in ids}
        for name, cid_set in by_name.items():
            if len(cid_set) != 1 or name in linked_names:
                continue
            c = cards[next(iter(cid_set))]
            plain = c.get("_plain", "auto")
            if plain is False:
                continue
            distinctive = len(name.split()) > 1 or name.startswith("\"") or plain is True
            if distinctive and re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text):
                ids.add(c["id"])
        for extra in cur.get("rulingCards", {}).get(r["id"], []):
            ids.add(extra)
        for drop in cur.get("rulingCardsRemove", {}).get(r["id"], []):
            ids.discard(drop)
        r["cards"] = sorted(i for i in ids if i in cards)
        for i in r["cards"]:
            cards[i]["rulings"].append(r["id"])

    for c in cards.values():
        c.pop("_plain", None)

    # 5. full card catalogue + text from YASB (if data/yasb/yasb-cards.json exists)
    pdf_card_count = len(cards)
    cards, yasb_info = yasb_cards.merge(cards, rulings, errata, cur)
    if yasb_info:
        (ROOT / "data" / "yasb" / "match-report.json").write_text(json.dumps(
            {"pdfCardsWithoutYasbMatch": yasb_info["unmatched"], "matches": yasb_info["remap"]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"YASB: {len(cards)} cards total; {pdf_card_count - len(yasb_info['unmatched'])} of "
              f"{pdf_card_count} PDF cards matched (unmatched: {', '.join(yasb_info['unmatched']) or 'none'})")
    # 6. official answers from the XWA rules forum (data/forum/threads.json)
    forum, forum_info = forum_rulings.to_rulings(cards, skip_extra=epic.get("forumThreads", []))
    for r in forum:
        for i in r["cards"]:
            cards[i]["rulings"].append(r["id"])
    rulings = rulings + forum

    # banned cards (data/banned-cards.json): per card, a list of {format, where, note, since, stagingTest}
    ban_path = ROOT / "data" / "banned-cards.json"
    bans = json.loads(ban_path.read_text(encoding="utf-8")).get("cards", {}) if ban_path.exists() else {}
    for cid, entries in bans.items():
        if cid not in cards:
            print(f"WARNING: banned-cards.json names unknown card {cid}")
            continue
        clean = []
        for b in entries if isinstance(entries, list) else [entries]:
            where = b.get("where", "all")
            clean.append({k: v for k, v in {"format": b.get("format", "Standard"),
                                             "where": "all" if where in ("all", None, []) else list(where),
                                             "note": b.get("note"), "since": b.get("since"),
                                             "stagingTest": bool(b.get("stagingTest"))}.items() if v})
        cards[cid]["bans"] = clean
    if bans:
        print(f"Banned cards: {len(bans)} "
              f"({sum(1 for v in bans.values() if all(b.get('stagingTest') for b in v))} staging-only tests)")

    # rulings kept for reference but no longer current (data/deprecated-rulings.json)
    dep_path = ROOT / "data" / "deprecated-rulings.json"
    deprecated = json.loads(dep_path.read_text(encoding="utf-8")).get("rulings", {}) if dep_path.exists() else {}
    by_id = {r["id"]: r for r in rulings}
    for rid, info in deprecated.items():
        if rid not in by_id:
            print(f"WARNING: deprecated-rulings.json names unknown ruling {rid}")
            continue
        by_id[rid]["deprecated"] = {k: info.get(k) for k in ("asOf", "reason", "replacedBy", "stagingTest") if info.get(k)}
    if deprecated:
        print(f"Outdated rulings: {len(deprecated)} "
              f"({sum(1 for v in deprecated.values() if v.get('stagingTest'))} staging-only tests)")
    if forum_info:
        report = {r["id"]: {"topic": r["topic"], "cards": [cards[i]["name"] + " — " + i for i in r["cards"]]} for r in forum}
        (ROOT / "data" / "forum" / "match-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                                    encoding="utf-8")
        print(f"Forum: {len(forum)} rules-team answers; {sum(1 for r in forum if not r['cards'])} not tied to a card")

    for c in cards.values():
        for k in [k for k, v in c.items() if v is None or v == [] and k not in ("rulings", "errata", "factions")]:
            del c[k]

    # 7. the numbered Compendium (also writes site/compendium.txt)
    comp = compendium.build(rules, rulings, errata, sources["documents"], cards)
    (ROOT / "data" / "compendium-report.json").write_text(json.dumps(comp["placement"], ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
    print(f"Compendium: {len(comp['sections'])} sections, {len(comp['refs'])} numbered paragraphs")

    # 8. playtest cards + rulings (data/playtest.json): kept apart from the official data and only
    #    shown on the playtest site (sample entries: on staging's playtest preview). See docs/MAINTAINING.md.
    playtest = load_playtest(cards)

    data = {
        "meta": {"sources": [{k: s.get(k) for k in ("id", "title", "version", "effective", "url")}
                             for s in sources["documents"]],
                 "otherDocuments": [{k: s.get(k) for k in ("title", "version", "effective", "url")}
                                    for s in sources.get("otherDocuments", [])],
                 "hideEpic": bool(sources.get("hideEpic")),
                 "quizLive": bool(sources.get("quizLive")),
                 "quizSkip": sources.get("quizSkip", []),
                 "documentsPage": sources.get("documentsPage") or None,
                 "reportForm": sources.get("reportForm") or None,
                 "cardData": {k: yasb_info[k] for k in ("source", "commit", "importedAt")} if yasb_info else None,
                 "forum": forum_info},
        "rules": rules,
        "rulings": rulings,
        "errata": errata,
        "cards": sorted(cards.values(), key=lambda c: c["name"].strip("\"").lower()),
        "compendium": {"sections": comp["sections"], "refs": comp["refs"]},
        "playtest": playtest,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("// Generated by tools/build_data.py - do not edit by hand.\n"
                   "window.ARCHIVES = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    (ROOT / "data" / "unmatched-mentions.json").write_text(
        json.dumps(unmatched, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"rules={len(rules)} rulings={len(rulings)} errata={len(errata)} cards={len(cards)} "
          f"unmatched={len(unmatched)}  (unmatched list: data/unmatched-mentions.json)")


if __name__ == "__main__":
    main()
