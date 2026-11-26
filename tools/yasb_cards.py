"""
Adds the full card catalogue from YASB (data/yasb/yasb-cards.json, made by
tools/import_yasb.js) to the cards found in the rules PDFs.

Every YASB pilot, upgrade, ship ability, condition and damage card becomes a card.
Cards that the PDFs mention (with their rulings and errata) are matched to the
YASB card with the same name + ship (pilots) or name + slot (upgrades).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YASB = ROOT / "data" / "yasb" / "yasb-cards.json"

ICON_WORDS = {
    "ROTATEARC": "rotate", "DEVICE": "payload", "SINGLETURRETARC": "singleturretarc",
    "DOUBLETURRETARC": "doubleturretarc", "FORCEPOWER": "forcepower",
}
ACTION_TOKENS = {
    "Focus": "focus", "Lock": "lock", "Barrel Roll": "barrelroll", "Boost": "boost", "Evade": "evade",
    "Cloak": "cloak", "Reinforce": "reinforce", "Coordinate": "coordinate", "Jam": "jam", "Slam": "slam",
    "SLAM": "slam", "Calculate": "calculate", "Reload": "reload", "Rotate Arc": "rotate",
}
SLOT_TOKEN = {
    "Talent": "talent", "Sensor": "sensor", "Cannon": "cannon", "Turret": "turret", "Torpedo": "torpedo",
    "Missile": "missile", "Hardpoint": "hardpoint", "Crew": "crew", "Team": "team", "Astromech": "astromech",
    "Cargo": "cargo", "Device": "payload", "Payload": "payload", "Command": "command", "Illicit": "illicit",
    "Modification": "modification", "Title": "title", "Tech": "tech", "Configuration": "configuration",
    "Force": "forcepower", "Force Power": "forcepower", "Gunner": "gunner", "Tactical Relay": "tacticalrelay",
    "HardpointShip": "hardpoint", "Hyperdrive": "hyperdrive",
}
SLOT_DISPLAY = {"Device": "Payload", "Force": "Force Power"}


def slug(s):
    s = s.lower().replace("’", "").replace("'", "").replace("é", "e").replace("é", "e")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


PAREN = re.compile(r"\s*\(([^)]*)\)\s*$")


def bare(s):
    """'Iden Versio (BoY)' -> 'Iden Versio'"""
    return PAREN.sub("", s or "")


def paren(s):
    m = PAREN.search(s or "")
    return m.group(1) if m else None


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("é", "e"))


def convert_text(t):
    """YASB markup -> Archives markup: {icon} tokens, **bold**, newlines. Returns (text, flavor)."""
    if not t:
        return None, None
    flavor = None
    m = re.search(r"<i class ?= ?\"?flavor_text\"?>(.*?)</i>", t, re.S)
    if m:
        flavor = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        t = t[:m.start()] + t[m.end():]
    t = re.sub(r"<i>\s*Errata[^<]*</i>", "", t)
    t = re.sub(r"%([A-Z_]+)%", lambda m: "\n" if m.group(1) == "LINEBREAK"
               else "{" + ICON_WORDS.get(m.group(1), m.group(1).lower()) + "}", t)
    t = re.sub(r'<i class="xwing-miniatures-font xwing-miniatures-font-([a-z]+)"[^>]*></i>', r"{\1}", t)
    t = re.sub(r"<(strong|b)>(.*?)</\1>", lambda m: "**" + m.group(2).strip() + "**", t, flags=re.S)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = "\n".join(line.strip() for line in t.split("\n") if line.strip())
    return (t or None), flavor


def action_list(actions):
    """['R-> Focus', 'Boost'] -> [{'a': 'focus', 'red': True, 'linked': True}, ...]"""
    out = []
    for a in actions or []:
        m = re.match(r"^(R-|F-)?(> ?)?(.+)$", a.lstrip("*"))   # "*X" = first of a linked pair (upgrades)
        color, linked, name = m.groups()
        out.append({"a": ACTION_TOKENS.get(name, slug(name)), "c": {"R-": "red", "F-": "purple"}.get(color, "white"),
                    "linked": bool(linked)})
    return out


def restriction_text(r):
    if not r:
        return None
    parts = []
    for item in r:
        if not isinstance(item, list) or not item:
            continue
        kind, *vals = item
        vals = [str(v) for v in vals]
        if kind == "Base":
            parts.append(" or ".join(vals) + " ship")
        elif kind == "Action":
            parts.append("Requires " + " or ".join(vals).replace("R-", "red ") + " action")
        elif kind == "Slot":
            parts.append("Requires " + " or ".join(vals) + " slot")
        elif kind == "Keyword":
            parts.append(" or ".join(vals))
        elif kind == "Equipped":
            parts.append("Requires equipped " + " or ".join(vals))
        elif kind == "isUnique":
            parts.append("Limited ship")
        elif kind == "FactionOrUnique":
            parts.append(" or ".join(vals))
        else:
            parts.append(re.sub(r"([a-z])([A-Z])", r"\1 \2", kind) + (" " + " ".join(vals) if vals else ""))
    return ", ".join(parts) or None


def stat_block(obj):
    keys = {"attack": "frontarc", "attackf": "fullfrontarc", "attackb": "reararc", "attackt": "singleturretarc",
            "attackdt": "doubleturretarc", "attackbull": "bullseyearc", "attackl": "leftarc", "attackr": "rightarc"}
    attacks = [{"arc": arc, "v": obj[k]} for k, arc in keys.items() if k in obj]
    out = {"attacks": attacks}
    for k in ("agility", "hull", "shields", "energy"):
        if k in obj:
            out[k] = obj[k]
    return out


def load_yasb():
    if not YASB.exists():
        return None
    return json.loads(YASB.read_text(encoding="utf-8"))


def yasb_cards(d):
    """Return a list of Archives card dicts built from YASB data, with a 'base' key for matching."""
    tr = d["translations"]
    ships = d["ships"]
    chassis_text = {k: v for k, v in tr["chassis_translations"].items()}
    cards = []

    # ship abilities (chassis)
    chassis_ships = {}
    for sname, s in ships.items():
        if s.get("chassis"):
            chassis_ships.setdefault(s["chassis"], []).append(sname)
    for p in d["pilotsById"]:
        if p.get("chassis") and p.get("ship"):
            chassis_ships.setdefault(p["chassis"], [])
            if p["ship"] not in chassis_ships[p["chassis"]]:
                chassis_ships[p["chassis"]].append(p["ship"])
    for c in d["chassisById"]:
        name = c.get("name")
        if not name or c.get("skip"):
            continue
        t = chassis_text.get(name, {})
        text, flavor = convert_text(t.get("text"))
        sh = chassis_ships.get(name, [])
        cards.append({"base": slug(t.get("display_name") or name), "name": t.get("display_name") or name,
                      "type": "Ship Ability", "ship": ", ".join(sh) or None, "text": text, "yasbKey": name,
                      "factions": sorted({f for s in sh if s in ships for f in ships[s]["factions"]})})

    for p in d["pilotsById"]:
        name = p.get("name")
        if not name or p.get("skip"):
            continue
        t = tr["pilot_translations"].get(name, {})
        disp = t.get("display_name") or p.get("display_name") or re.sub(r"\s*\((?:[^)]*)\)$", "", name)
        text, flavor = convert_text(t.get("text"))
        ship = ships.get(p["ship"], {})
        so = p.get("ship_override") or {}
        merged = dict(ship, **so)
        chassis = p.get("chassis") or ship.get("chassis")
        card = {
            "base": f"{slug(bare(disp))}-{slug(p['ship'])}", "name": disp, "type": "Pilot", "ship": p["ship"],
            "factions": [p["faction"]], "yasbKey": name, "text": text, "flavor": flavor,
            "limited": 1 if p.get("unique") else p.get("max_per_squad"),
            # points / loadout values are deliberately not imported: they change several
            # times a year and this site is about rulings, not squad building.
            "initiative": p.get("skill"),
            # upgrade bars are also left out: they change with points updates
            "charge": p.get("charge"), "force": p.get("force"),
            # Force recurs 1 per round unless YASB says otherwise (forcerecurring: 0)
            "forceRecurring": p.get("forcerecurring", 1) if p.get("force") else None,
            "recurring": p.get("recurring"), "keywords": p.get("keyword"), "engagement": p.get("engagement"),
            "stats": stat_block(merged), "actions": action_list(merged.get("actions")),
            "dial": ship.get("maneuvers"), "shipAbility": None, "standardUpgrades": p.get("upgrades"),
            "base_size": ship.get("base"),
        }
        if chassis:
            ct = chassis_text.get(chassis, {})
            card["shipAbility"] = {"name": ct.get("display_name") or chassis, "text": convert_text(ct.get("text"))[0],
                                   "id": slug(ct.get("display_name") or chassis)}
        if p.get("upgrades"):
            card["loadout"] = "Standard loadout"
        cards.append(card)

    for u in d["upgradesById"]:
        name = u.get("name")
        if not name or u.get("skip"):
            continue
        t = tr["upgrade_translations"].get(name, {})
        disp = t.get("display_name") or u.get("display_name") or re.sub(r"\s*\((?:BoY|[^)]*)\)$", "", name)
        text, flavor = convert_text(t.get("text"))
        slots = [u["slot"]] + [s for s in (u.get("also_occupies_upgrades") or []) if s != u["slot"]]
        fac = u.get("faction")
        factions = fac if isinstance(fac, list) else ([fac] if fac else [])
        slot_names = [SLOT_DISPLAY.get(s, s) for s in slots]
        card = {
            "base": f"{slug(bare(disp))}-{slug(slot_names[0])}", "name": disp, "type": "Upgrade", "slot": slot_names,
            "factions": factions, "yasbKey": name, "text": text, "flavor": flavor,
            "limited": 1 if u.get("unique") else u.get("max_per_squad"),
            "charge": u.get("charge"), "force": u.get("force"), "recurring": u.get("recurring"),
            "forceRecurring": u.get("forcerecurring", 1) if u.get("force") else None,
            "restriction": restriction_text(u.get("restrictions")),
            # actions added to the ship's action bar; two-sided cards already show each side's actions in their text
            "actions": (None if re.search(r"\*\*(Closed|Open|Attached|Detached):\*\*\s*\{", text or "")
                        else action_list(u.get("addActions")) or None),
            "restrictedShip": u.get("ship"), "solitary": u.get("solitary"), "standardized": u.get("standardized"),
            "weapon": ({"arc": next((a["arc"] for a in stat_block(u)["attacks"]), None),
                        "v": next((a["v"] for a in stat_block(u)["attacks"]), None),
                        "range": u.get("range"), "rangebonus": bool(u.get("rangebonus"))}
                       if any(k.startswith("attack") for k in u) else None),
        }
        if "(BoY)" in name or u.get("standard"):
            card["loadout"] = "Standard loadout"
        cards.append(card)

    for c in d["conditionsById"]:
        name = c.get("name")
        if not name or c.get("skip"):
            continue
        t = tr["condition_translations"].get(name, {})
        text, flavor = convert_text(t.get("text"))
        cards.append({"base": slug(name), "name": t.get("display_name") or name, "type": "Condition",
                      "yasbKey": name, "text": text, "factions": [], "limited": 1 if c.get("unique") else None})

    for c in d["damageById"]:
        name = c.get("name")
        if not name:
            continue
        t = tr["damage_translations"].get(name, {})
        text, _ = convert_text(t.get("text"))
        cards.append({"base": slug(name), "name": name, "type": "Damage Card", "yasbKey": name, "text": text,
                      "factions": [], "damageType": c.get("type"), "quantity": c.get("quantity")})
    return cards


def assign_ids(ycards):
    """Cards sharing a name+ship/slot get distinct ids: the plain printing keeps the
    short id, variants get a suffix from their YASB name, e.g. iden-versio-tie-in-interceptor-boy."""
    groups = {}
    for c in ycards:
        groups.setdefault(c["base"], []).append(c)
    for base, cs in groups.items():
        used = set()
        plain = [c for c in cs if not paren(c["yasbKey"])]
        if len(plain) == 1:
            plain[0]["id"] = base
            used.add(base)
        for c in cs:
            if c.get("id"):
                continue
            tries = []
            if paren(c["yasbKey"]):
                tries.append(f"{base}-{slug(paren(c['yasbKey']))}")
            if c.get("factions"):
                tries.append(f"{base}-{slug(c['factions'][0])}")
            tries.append(base)
            cid = next((t for t in tries if t not in used), None)
            n = 2
            while cid is None or cid in used:
                cid = f"{base}-{n}"
                n += 1
            c["id"] = cid
            used.add(cid)
    return groups


def pdf_base(c):
    """Matching key for a card that came from the PDFs."""
    n = slug(c["name"])
    if c["type"] == "Pilot" and c.get("ship"):
        return f"{n}-{slug(c['ship'])}"
    if c["type"] in ("Upgrade",) and c.get("slot"):
        return f"{n}-{slug(c['slot'][0])}"
    return n


def merge(cards, rulings, errata, curated):
    """cards: dict id->card built from the PDFs. Returns new dict id->card with YASB data merged in."""
    d = load_yasb()
    if d is None:
        return cards, None
    ycards = yasb_cards(d)
    groups = assign_ids(ycards)
    by_name = {}
    for c in ycards:
        by_name.setdefault((norm_name(bare(c["name"])), c["type"]), []).append(c)
    ship_alias = {norm_name(k): v for k, v in curated.get("yasbShipAliases", {}).items()}

    out = {c["id"]: dict(c, rulings=[], errata=[], aliases=[], origin="yasb") for c in ycards}
    remap = {}
    unmatched = []
    for old_id, pc in cards.items():
        if old_id in curated.get("yasbMatch", {}) and not old_id.startswith("_"):
            targets = curated["yasbMatch"][old_id]
            targets = [] if targets is None else targets if isinstance(targets, list) else [targets]
        else:
            base = pdf_base(pc)
            if pc.get("ship") and norm_name(pc["ship"]) in ship_alias:
                base = f"{slug(pc['name'])}-{slug(ship_alias[norm_name(pc['ship'])])}"
            cands = list(groups.get(base, []))
            if not cands:
                # fall back to name + type (e.g. pilots whose ship the PDF didn't name)
                t = pc["type"] if pc["type"] != "Standard Loadout" else "Pilot"
                cands = list(by_name.get((norm_name(pc["name"]), t), []))
                if not cands and t == "Upgrade":
                    # slot named differently (e.g. PDF says Crew, YASB says Command)
                    cands = [c for c in by_name.get((norm_name(pc["name"]), "Upgrade"), [])]
                if not cands:
                    cands = [c for (n, _), cs in by_name.items() if n == norm_name(pc["name"]) for c in cs]
                if pc.get("ship") and len(cands) > 1:
                    def overlap(c):
                        a = set(re.findall(r"[a-z0-9]+", pc["ship"].lower()))
                        b = set(re.findall(r"[a-z0-9]+", (c.get("ship") or "").lower()))
                        return len(a & b)
                    best = max(overlap(c) for c in cands)
                    cands = [c for c in cands if overlap(c) == best and best > 0]
            if len(cands) > 1 and pc.get("factions"):
                f = [c for c in cands if set(c.get("factions") or []) & set(pc["factions"])]
                cands = f or cands
            if len(cands) > 1:
                want_std = pc["type"] == "Standard Loadout" or bool(pc.get("loadout"))
                f = [c for c in cands if bool(c.get("loadout")) == want_std]
                cands = f or cands
            if len(cands) > 1:
                f = [c for c in cands if not paren(c["yasbKey"])]
                cands = f if len(f) == 1 else cands
            targets = [c["id"] for c in cands]
        if not targets:
            out[old_id] = pc
            unmatched.append(old_id)
            continue
        remap[old_id] = targets
        for t in targets:
            yc = out[t]
            for k in ("rulings", "errata"):
                yc[k] += [x for x in pc[k] if x not in yc[k]]
            yc["aliases"] += [a for a in pc.get("aliases", []) if a not in yc["aliases"]]
            # a PDF card pointed at a differently named card (e.g. "Admiral Holdo" -> Amilyn Holdo):
            # keep the PDF's name as an alias so the ruling text still links and search finds it
            if norm_name(bare(pc["name"])) != norm_name(bare(yc["name"])) and pc["name"] not in yc["aliases"]:
                yc["aliases"].append(pc["name"])
            if not yc.get("text") and pc.get("text"):
                yc["text"] = pc["text"]

    # rewrite references in rulings / errata
    for coll in (rulings, errata):
        for item in coll:
            new = []
            for i in item.get("cards", []):
                for t in remap.get(i, [i]):
                    if t not in new:
                        new.append(t)
            item["cards"] = new

    # link ship-ability cards to pilots that have them
    for c in out.values():
        if c.get("shipAbility") and c["shipAbility"]["id"] not in out:
            c["shipAbility"]["id"] = None
    for c in out.values():
        c.pop("base", None)
    info = {"source": d["source"], "commit": d["commit"], "importedAt": d["importedAt"],
            "unmatched": unmatched, "remap": remap}
    return out, info
