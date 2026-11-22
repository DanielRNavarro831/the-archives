"""
Write docs/related-rulings-review.md from data/related-rulings.json: a checklist of rulings that may
also apply to cards they don't name, with each card's text, for review before anything is linked.
Run after tools/build_data.py:

    python tools/related_review.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import related_group_cards  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    s = (ROOT / "site" / "data" / "archives.js").read_text(encoding="utf-8")
    db = json.loads(s[s.index("{"):s.rindex("}") + 1])
    cards = {c["id"]: c for c in db["cards"]}
    rulings = {r["id"]: r for r in db["rulings"]}
    sugg = json.loads((ROOT / "data" / "related-rulings.json").read_text(encoding="utf-8"))

    def label(c):
        extra = c.get("ship") or " / ".join(c.get("slot") or []) or c.get("type", "")
        return f"**{c['name']}** ({extra})"

    def text(c):
        return re.sub(r"\s+", " ", (c.get("text") or "").replace("**", "")).strip()   # full text: never shortened

    out = ["# Related rulings: suggestions to review", "",
           "Each ruling below names some cards; these are other cards whose text uses the same mechanic.",
           "Nothing here is on the site yet. Tick the cards that should show the ruling (or cross out the ones",
           "that shouldn't) and send it back. Approved links would show on a card page under",
           "\"Rulings that may also apply\", with a note that the ruling doesn't name that card.", ""]
    total = 0
    for rid, e in sugg["rulings"].items():
        r = rulings[rid]
        named = ", ".join(sorted({cards[i]["name"] for i in r["cards"] if i in cards})) or "none"
        out += [f"## {rid}: {e['mechanic']}", "",
                f"> **Q:** {r['q']}", ">", f"> **A:** {' '.join(r['a'])}", "",
                f"Already named: {named}", ""]
        if e.get("onHold"):
            out += [f"**ON HOLD:** {e['onHold']}", ""]
        for g in e["groups"]:
            status = {"approved": " — APPROVED, on the site", "rejected": " — SKIPPED"}.get(g.get("status"), "")
            out += [f"**{g['why']}** ({g['strength']} match){status}", ""]
            box = {"approved": "[x]", "rejected": "[-]"}.get(g.get("status"), "[ ]")
            ids = related_group_cards(g, cards)
            if g.get("match"):
                out.append(f"- {box} {len(ids)} cards: " + ", ".join(sorted({f'{cards[i]["name"]} ({cards[i].get("ship") or " / ".join(cards[i].get("slot") or [])})' for i in ids})))
                total += len(ids)
            for i in ([] if g.get("match") else ids):
                c = cards[i]
                out.append(f"- {box} {label(c)}: {text(c)}")
                total += 1
            out.append("")
    out += ["## Looked at but not suggested", ""]
    for ids, why in sugg.get("notSuggested", {}).items():
        names = ", ".join(cards[i]["name"] for i in ids.split(", ") if i in cards)
        out.append(f"- {names}: {why}")
    out.append("")
    (ROOT / "docs" / "related-rulings-review.md").write_text("\n".join(out), encoding="utf-8")
    print(f"{total} suggested links across {len(sugg['rulings'])} rulings -> docs/related-rulings-review.md")


if __name__ == "__main__":
    main()
