"""Mapping from the X-Wing icon font used in the official PDFs to the
{token} names used in The Archives' data files.

The PDFs store each icon as a private-use character 0xF2000 + offset.
Unknown icons become {icon-XXX} so they are easy to spot and add here.
"""

ICON_OFFSETS = {
    # actions
    0x040: "focus", 0x041: "lock", 0x042: "barrelroll", 0x043: "boost",
    0x044: "evade", 0x045: "cloak", 0x047: "reinforce", 0x048: "coordinate",
    0x049: "jam", 0x04A: "slam", 0x225: "calculate", 0x223: "reload",
    0x06B: "rotate", 0x224: "linked",
    # upgrade slots
    0x04B: "talent", 0x04C: "sensor", 0x04D: "cannon", 0x04E: "turret",
    0x04F: "torpedo", 0x050: "missile", 0x051: "hardpoint", 0x052: "crew",
    0x053: "team", 0x054: "astromech", 0x055: "cargo", 0x056: "payload",
    0x057: "command", 0x058: "illicit", 0x059: "modification", 0x05A: "title",
    0x05B: "tech", 0x221: "configuration", 0x222: "forcepower",
    0x226: "gunner", 0x402: "tacticalrelay", 0x500: "hyperdrive",
    # maneuvers
    0x05C: "turnleft", 0x05D: "bankleft", 0x05E: "straight", 0x05F: "bankright",
    0x060: "turnright", 0x061: "stop", 0x062: "trollleft", 0x063: "sloopleft",
    0x064: "kturn", 0x065: "sloopright", 0x066: "trollright",
    0x06C: "reversestraight", 0x06D: "reversebankright", 0x06E: "reversebankleft",
    # dice
    0x067: "hit", 0x068: "crit",
    # charges & stats
    0x06A: "energy", 0x22E: "charge", 0x22F: "force", 0x408: "shield",
    0x409: "threat", 0x406: "objective",
    0x405: "command", 0x407: "objectivemarker",   # Epic rules: command symbol, objective marker
    # arcs
    0x227: "fullfrontarc", 0x228: "fullreararc", 0x229: "bullseyearc",
    0x22A: "reararc", 0x22B: "frontarc", 0x22C: "doubleturretarc",
    0x22D: "singleturretarc", 0x400: "leftarc", 0x401: "rightarc",
    0x5C0: "singleturretarc",
}


def icon_token(codepoint: int) -> str:
    off = codepoint - 0xF2000
    name = ICON_OFFSETS.get(off)
    if name:
        return "{" + name + "}"
    return "{icon-%x}" % off
