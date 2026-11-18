"""
Download the latest YASB card data files from GitHub (github.com/raithos/xwing, MIT License).

    python tools/fetch_yasb.py

Saves cards-common.coffee, cards-en.coffee, LICENSE and the commit id to data/yasb/source/.
The files are data for tools/import_yasb.js, which only parses them (never runs them).
"""
import json
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "data" / "yasb" / "source"
REPO = "raithos/xwing"
FILES = {
    "cards-common.coffee": "coffeescripts/content/cards-common.coffee",
    "cards-en.coffee": "coffeescripts/content/cards-en.coffee",
    "LICENSE": "LICENSE",
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "the-archives-updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    sha = json.loads(get(f"https://api.github.com/repos/{REPO}/commits/master"))["sha"]
    old = (DEST / "COMMIT").read_text().strip() if (DEST / "COMMIT").exists() else None
    print(f"latest YASB commit: {sha}" + (" (no change)" if sha == old else f" (was {old})"))
    for name, path in FILES.items():
        data = get(f"https://raw.githubusercontent.com/{REPO}/{sha}/{path}")
        (DEST / name).write_bytes(data)
        print(f"  {name}: {len(data):,} bytes")
    (DEST / "COMMIT").write_text(sha + "\n")


if __name__ == "__main__":
    main()
