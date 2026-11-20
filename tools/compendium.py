"""
Builds the Compendium: every Rules Reference entry, FAQ answer, XWA rules-team forum
answer and erratum in one numbered document, grouped by topic.

Each paragraph gets a reference like §23.4 (section 23, paragraph 4), so a ruling can be
cited and looked up exactly. Text is never rewritten: paragraphs point at the original
rules/rulings/errata, and the plain-text export copies them word for word.

Placing rulings under a topic is done with fixed rules, not guesswork:
  1. FAQ headings map to a topic (e.g. "Locking" -> Lock).
  2. Otherwise the topic whose glossary term the question uses most specifically wins.
  3. data/compendium-curated.json can move any ruling by hand.
Used by build_data.py; also writes site/compendium.txt.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURATED = ROOT / "data" / "compendium-curated.json"
TXT = ROOT / "site" / "compendium.txt"

# FAQ headings -> glossary title
FAQ_TOPIC = {
    "Arcs": "Arc", "Deployment": "Deploy", "List Building": "Upgrade Cards", "Locking": "Lock",
    "Objects": "Objects", "Damage Cards": "Damage Cards", "Rolling and Rerolling Dice": "Dice Modification",
    "Abilities and the Ability Queue": "Ability Queue", "Engagement Phase and Attacking": "Attack",
    "Activation Phase and Actions": "Actions",
}
HUGE_FAQ_TOPIC = {"Attacks": "Attacks", "Movement": "Movement", "Turret Arc Indicator Placement": "Turret Arc Indicators"}

# Terms too common to decide a topic on their own (they still count, just a little)
GENERIC = {"ship", "attack", "defender", "defend", "range", "round", "move", "target", "friendly", "enemy",
           "abilities", "actions", "damage", "dial", "maneuver", "speed", "tokens", "unit", "supply", "miss",
           "hit", "fail", "timing", "direction", "arc", "activation", "reveal", "setup", "ship type",
           "faction", "initiative", "agility", "hull", "objects", "card interpretation", "introduction",
           "golden rules", "errata and conflicts", "turn", "straight", "bank", "cancel", "break", "inflict",
           "game mode", "guides", "allied", "miniatures", "title", "remotes"}
INTRO = ["Introduction", "Golden Rules", "Card Interpretation", "Errata and Conflicts"]


def term_patterns(title):
    """'Bonus Attack' -> regex matching bonus attack(s); 'Lock' -> lock/locks/locked/locking."""
    t = re.sub(r"\s*\(.*?\)", "", title).lower().replace("’", "'")
    words = t.split()
    last = re.escape(words[-1])
    stem = r"(?:s|es|ed|ing|d)?"
    if last.endswith("e"):
        stem = r"(?:s|d)?"          # "mine" must not match "mining"
    body = r"\s+".join(re.escape(w) for w in words[:-1]) + (r"\s+" if len(words) > 1 else "") + last + stem
    return re.compile(r"(?<![\w-])" + body + r"(?![\w-])", re.I)


LABELS = {"barrelroll": "Barrel Roll", "forcepower": "Force Power", "tacticalrelay": "Tactical Relay",
          "frontarc": "Front Arc", "reararc": "Rear Arc", "fullfrontarc": "Full Front Arc", "fullreararc": "Full Rear Arc",
          "bullseyearc": "Bullseye Arc", "singleturretarc": "Turret Arc", "doubleturretarc": "Double Turret Arc",
          "leftarc": "Left Arc", "rightarc": "Right Arc", "bankleft": "Bank Left", "bankright": "Bank Right",
          "turnleft": "Turn Left", "turnright": "Turn Right", "kturn": "Koiogran Turn", "sloopleft": "Segnor's Loop Left",
          "sloopright": "Segnor's Loop Right", "trollleft": "Tallon Roll Left", "trollright": "Tallon Roll Right",
          "reversestraight": "Reverse Straight", "reversebankleft": "Reverse Bank Left", "reversebankright": "Reverse Bank Right",
          "stop": "Stop", "slam": "SLAM", "rangebonus": "Range Bonus", "linked": ">"}


def plain(text):
    """{focus} -> [Focus] for the text export."""
    return re.sub(r"\{([a-z-]+)\}", lambda m: "[" + LABELS.get(m.group(1), m.group(1).replace("-", " ").title()) + "]", text or "")


def build(rules, rulings, errata, sources, cards):
    cur = json.loads(CURATED.read_text(encoding="utf-8")) if CURATED.exists() else {}
    moves = cur.get("moveRuling", {})
    src_by_id = {s["id"]: s for s in sources}

    # ---- sections: intro, glossary A-Z (with 1.4 update entries), appendices, errata
    rr = [r for r in rules if r["source"] == "rr"]
    gloss = [r for r in rr if r["sectionId"] in ("glossary", "update") and r["title"] not in INTRO]
    gloss.sort(key=lambda r: re.sub(r"[^a-z0-9 ]", "", r["title"].lower()))
    intro = [r for r in rr if r["title"] in INTRO and r["sectionId"] == "glossary"]
    appx = [r for r in rr if r["sectionId"] not in ("glossary", "update")]
    ordered = intro + gloss + appx

    sections = []
    by_title = {}
    for r in ordered:
        sec = {"n": len(sections) + 1, "title": r["title"], "group": r["section"], "rule": r["id"], "items": []}
        sections.append(sec)
        by_title.setdefault(r["title"].lower(), sec)
        if r["sectionId"] in ("huge",):
            by_title["huge:" + r["title"].lower()] = sec
    misc = {"n": len(sections) + 1, "title": "Other Rulings", "group": "Rulings", "rule": None, "items": []}
    sections.append(misc)
    errata_sec = {"n": len(sections) + 1, "title": "Errata", "group": "Errata", "rule": None, "items": []}
    sections.append(errata_sec)

    topics = [(sec, term_patterns(sec["title"])) for sec in sections[:len(intro) + len(gloss)]
              if sec["title"] not in INTRO]

    def topic_for(r):
        if r["id"] in moves:
            t = moves[r["id"]].lower()
            return by_title.get(t) or by_title.get("huge:" + t), "curated"
        if r["source"] == "rr" and r["section"] == "Huge Ship FAQ":
            return by_title.get("huge:" + HUGE_FAQ_TOPIC.get(r["topic"], "").lower()), "faq heading"
        if r["source"] == "rr" and r["topic"] in FAQ_TOPIC:
            return by_title.get(FAQ_TOPIC[r["topic"]].lower()), "faq heading"
        q = plain(r["q"]) + " " + (r.get("topic") if r["source"] == "forum" else "")
        a = plain(" ".join(r["a"]))
        best, best_score = None, 0.0
        for sec, pat in topics:
            hits_q, hits_a = len(pat.findall(q)), len(pat.findall(a))
            if not (hits_q or hits_a):
                continue
            tl = sec["title"].lower()
            if tl in GENERIC and tl not in ("attack", "range", "damage"):
                continue                # too vague to choose a topic by itself
            weight = 0.2 if tl in GENERIC else 1.0 + 0.5 * (len(sec["title"].split()) - 1)
            score = (3 * hits_q + hits_a) * weight
            if score > best_score:
                best, best_score = sec, score
        return (best, "terms") if best_score >= 1.0 else (None, "none")

    # ---- items: rule paragraphs first, then the rulings placed in that topic
    for sec in sections:
        if not sec["rule"]:
            continue
        rule = next(r for r in rules if r["id"] == sec["rule"])
        for i, b in enumerate(rule["blocks"]):
            if b["k"] == "h3":
                sec["items"].append({"kind": "heading", "ref": sec["rule"], "block": i})
            else:
                sec["items"].append({"kind": "rule", "ref": sec["rule"], "block": i})

    placement = {}
    for r in rulings:
        sec, why = topic_for(r)
        sec = sec or misc
        sec["items"].append({"kind": "ruling", "ref": r["id"]})
        placement[r["id"]] = {"section": sec["title"], "why": why}
    for e in errata:
        errata_sec["items"].append({"kind": "erratum", "ref": e["id"]})

    # ---- number the paragraphs (headings are not numbered)
    refs = {}
    for sec in sections:
        n = 0
        for it in sec["items"]:
            if it["kind"] == "heading":
                continue
            n += 1
            it["p"] = n
            key = f'{it["ref"]}#{it["block"]}' if it["kind"] == "rule" else it["ref"]
            refs[key] = f'{sec["n"]}.{n}'
    sections = [s for s in sections if s["items"]]

    edition = {"sources": [f'{s["title"]} v{s["version"]}' for s in sources if s["id"] == "rr"],
               "forumFetched": None}
    write_text(sections, rules, rulings, errata, src_by_id, cards, edition)
    return {"sections": sections, "refs": refs, "placement": placement}


def write_text(sections, rules, rulings, errata, src_by_id, cards, edition):
    R = {r["id"]: r for r in rules}
    RU = {r["id"]: r for r in rulings}
    E = {e["id"]: e for e in errata}
    out = ["THE ARCHIVES — COMPENDIUM",
           "Every Rules Reference entry, FAQ answer, XWA rules-team forum answer and erratum,",
           "numbered so each paragraph can be cited exactly (e.g. §23.4 = section 23, paragraph 4).",
           "Text is reproduced word for word. Sources: " + ", ".join(edition["sources"]) +
           ", XWA Rules Forum (rules team answers).",
           "Section numbers can change when the source documents are updated; cite the edition with the number.",
           "Unofficial fan reference. The official documents and your event's judge have the final word.", ""]
    out.append("CONTENTS")
    for s in sections:
        out.append(f'  §{s["n"]:<4} {s["title"]}' + (f'  ({s["group"]})' if s["group"] not in ("Glossary", "Rules Reference Update 1.4") else ""))
    out.append("")

    def cite(r):
        if r["source"] == "forum":
            who = ", ".join(f'{p["name"]} ({p["role"]})' for p in r.get("answeredBy", []))
            return f'XWA Rules Forum, answered by {who}, {r.get("date") or ""} — {r.get("url")}'
        s = src_by_id.get(r["source"], {})
        return f'{s.get("title")} v{s.get("version")}, p. {r.get("page")}, {r.get("section")} › {r.get("topic")}'

    for s in sections:
        out += ["", "=" * 72, f'§{s["n"]}  {s["title"].upper()}', "=" * 72]
        if s["rule"]:
            r = R[s["rule"]]
            out.append(f'[{src_by_id[r["source"]]["title"]} v{src_by_id[r["source"]]["version"]}, p. {r["page"]} — {r["section"]}]')
        for it in s["items"]:
            if it["kind"] == "heading":
                out += ["", "  " + plain(R[it["ref"]]["blocks"][it["block"]]["t"]).upper()]
            elif it["kind"] == "rule":
                b = R[it["ref"]]["blocks"][it["block"]]
                if b["k"] == "fig":
                    out.append(f'{s["n"]}.{it["p"]}  [FIGURE — see the site or the PDF, p. {b["page"]}]'
                               + (f' Caption: {plain(b["cap"])}' if b.get("cap") else ""))
                else:
                    out.append(f'{s["n"]}.{it["p"]}  ' + plain(b["t"]))
            elif it["kind"] == "ruling":
                r = RU[it["ref"]]
                names = [cards[i]["name"] for i in r.get("cards", []) if i in cards]
                dep = r.get("deprecated")
                tag = (f'OUTDATED RULING (no longer current as of {dep["asOf"]})'
                       if dep and not dep.get("stagingTest") else "RULING")
                out += ["", f'{s["n"]}.{it["p"]}  {tag} [{cite(r)}]' + (f'  Cards: {", ".join(names)}' if names else ""),
                        "      Q: " + plain(r["q"]).replace("\n", "\n         "),
                        "      A: " + "\n         ".join(plain(a) for a in r["a"])]
            elif it["kind"] == "erratum":
                e = E[it["ref"]]
                names = ", ".join(n.lstrip("•") for n in e["names"]) or e["category"]
                s_ = src_by_id.get(e["source"], {})
                out += ["", f'{s["n"]}.{it["p"]}  ERRATUM — {names}' + (f' ({e["qualifier"]})' if e.get("qualifier") else "") +
                        f' [{s_.get("title")} v{s_.get("version")}, p. {e["page"]}]',
                        "      " + "\n      ".join(plain(t) for t in e["text"])] + \
                       ([f'      ({plain(e["note"])})'] if e.get("note") else [])
    TXT.write_text("\n".join(out) + "\n", encoding="utf-8")
