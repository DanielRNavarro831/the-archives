"""
Turns data/forum/threads.json (made by tools/fetch_forum.py) into rulings and attaches
them to cards. Used by build_data.py.

Only replies from XWA rules team members (the "RULES" badge) count. Maui is the XWA
rules lead: his answers are listed first and labelled as such.
Thread-by-thread fixes (skip a thread, add/remove a card) live in data/forum-curated.json.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THREADS = ROOT / "data" / "forum" / "threads.json"
CURATED = ROOT / "data" / "forum-curated.json"

RULES_LEAD = "Maui"
PLACEHOLDER = re.compile(r"(answer soon|will answer|we'?ll get back|looking into (it|this)|under review)", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("é", "e"))


def to_rulings(cards_by_id, skip_extra=()):
    if not THREADS.exists():
        return [], None
    data = json.loads(THREADS.read_text(encoding="utf-8"))
    cur = json.loads(CURATED.read_text(encoding="utf-8")) if CURATED.exists() else {}
    skip = set(cur.get("skipThreads", {})) | {str(t) for t in skip_extra}
    add = cur.get("addCards", {})
    remove = cur.get("removeCards", {})

    cards = list(cards_by_id.values())
    by_name = {}
    for c in cards:
        for n in {c["name"], re.sub(r"\s*\([^)]*\)$", "", c["name"])} | set(c.get("aliases", [])):
            by_name.setdefault(norm(n), []).append(c)

    def pick(cands, hint=""):
        """Choose among same-named cards using an image file name like 'darthvader-tieddefender'."""
        if len(cands) <= 1:
            return cands
        h = norm(hint)
        if h:
            scored = []
            for c in cands:
                bits = norm(c.get("ship") or "") + norm(" ".join(c.get("slot") or [])) + norm(c.get("yasbKey"))
                variant = re.search(r"\(([^)]*)\)", c.get("yasbKey") or "")
                score = sum(1 for tok in re.findall(r"[a-z0-9]+", hint.lower().split("-", 1)[-1]) if tok in bits) if "-" in hint else 0
                if variant and norm(variant.group(1)) and norm(variant.group(1)) in h:
                    score += 3
                scored.append((score, c))
            best = max(s for s, _ in scored)
            if best > 0:
                return [c for s, c in scored if s == best]
        plain = [c for c in cands if not re.search(r"\([^)]*\)$", c.get("yasbKey") or "")]
        return plain if len(plain) == 1 else cands

    rulings = []
    for t in data["threads"]:
        if str(t["id"]) in skip:
            continue
        posts = t["posts"]
        if not posts:
            continue
        question = posts[0]
        answers = [p for p in posts[1:] if "RULES" in p["badges"] and not p.get("deleted")
                   and p["text"].strip() and not PLACEHOLDER.search(p["text"])]
        if not answers:
            continue
        answers.sort(key=lambda p: 0 if p["author"] == RULES_LEAD else 1)
        text = question["text"] + "\n" + " ".join(p["text"] for p in answers)

        ids = []
        # 1. card images embedded in the question/answers
        question_ids = []          # cards pictured in the asker's post (shown by the Judge Quiz)
        for pi, p in enumerate(posts):
            for img in p.get("cards", []):
                name = img["alt"].split(" — ")[0].strip().strip("“”\"")
                cands = by_name.get(norm(name)) or by_name.get(norm(img["alt"].replace("“", "\"").replace("”", "\""))) or []
                if not cands and img["alt"].startswith("“"):
                    cands = by_name.get(norm('"' + name + '"'), [])
                hint = (img.get("src") or "").rsplit("/", 1)[-1].rsplit(".", 1)[0]
                for c in pick(cands, hint):
                    if c["id"] not in ids:
                        ids.append(c["id"])
                    if pi == 0 and c["id"] not in question_ids:
                        question_ids.append(c["id"])
        # 2. distinctive card names written in the text (2+ words, or quoted like "Holo")
        flat = text.replace("“", "\"").replace("”", "\"").replace("’", "'")
        linked_names = {norm(cards_by_id[i]["name"]) for i in ids}
        for key, cands in by_name.items():
            if key in linked_names:
                continue
            c0 = cands[0]
            nm = c0["name"]
            if len(nm.split()) < 2 and not nm.startswith("\""):
                continue
            if re.search(r"(?<![\w])" + re.escape(re.sub(r"\s*\([^)]*\)$", "", nm)) + r"(?![\w])", flat, re.I):
                chosen = pick(cands)
                if len(chosen) <= 3:            # skip names shared by many cards (too vague)
                    for c in chosen:
                        if c["id"] not in ids:
                            ids.append(c["id"])
        for extra in add.get(str(t["id"]), []):
            if extra in cards_by_id and extra not in ids:
                ids.append(extra)
        ids = [i for i in ids if i not in set(remove.get(str(t["id"]), []))]

        lead = answers[0]
        rulings.append({
            "id": f"forum-{t['id']}", "source": "forum", "section": "XWA Rules Forum",
            "topic": t["title"], "url": t["url"],
            "q": question["text"], "a": [ln for p in answers for ln in p["text"].split("\n") if ln.strip()],
            "answeredBy": [{"name": p["author"], "role": "XWA Rules Lead" if p["author"] == RULES_LEAD else "XWA Rules Team",
                            "date": p.get("date")} for p in answers],
            "date": lead.get("date"),
            "cards": ids,
            "questionCards": [i for i in question_ids if i in ids],
        })
    info = {"source": data["source"], "fetched": data["fetched"], "count": len(rulings)}
    return rulings, info
