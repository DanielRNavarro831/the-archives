"""
Downloads the XWA forum's Rules Questions threads and keeps the official answers.

    python tools/fetch_forum.py

Reads https://www.xwing.life/forum/rules-questions (all pages) politely (1 request/second),
and writes data/forum/threads.json with, for every thread: title, link, the question, and
every reply with its author, badges and date.

Which replies count as rulings is decided later in build_data.py: only replies from
members with the "RULES" badge, ignoring placeholders like "we'll answer soon".
"""
import json
import re
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

BASE = "https://www.xwing.life"
SECTION = "/forum/rules-questions"
OUT = Path(__file__).resolve().parent.parent / "data" / "forum" / "threads.json"
UA = {"User-Agent": "the-archives-rulings-importer (fan rules reference)"}


def get(path):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    time.sleep(1)
    return BeautifulSoup(html, "html.parser")


def thread_ids():
    ids, page = [], 1
    while True:
        soup = get(f"{SECTION}?page={page}")
        found = [int(m.group(1)) for a in soup.select("a[href]")
                 if (m := re.fullmatch(rf"{SECTION}/(\d+)", a["href"]))]
        new = [i for i in dict.fromkeys(found) if i not in ids]
        if not new:
            break
        ids += new
        page += 1
    return ids


BADGES = {"RULES", "ADMIN", "MOD", "MODERATOR", "OP", "STAFF"}


def parse_thread(tid):
    soup = get(f"{SECTION}/{tid}")
    title = soup.find("h1")
    posts = []
    for art in soup.select("article[id^=post-]"):
        header = art.find("header")
        spans = [s.get_text(" ", strip=True) for s in header.find_all("span")] if header else []
        author = spans[0] if spans else None
        badges = sorted({s for s in spans if s.upper() in BADGES})
        dated = header.find(attrs={"title": re.compile(r"\d{4}")}) if header else None
        body = art.select_one(".forum-prose")
        cards = []
        text = ""
        if body:
            # card images the poster embedded: their captions name the exact card
            for img in body.find_all("img"):
                if img.get("alt"):
                    cards.append({"alt": img["alt"], "src": img.get("src")})
            for q in body.find_all("blockquote"):
                if q.find(class_="forum-mention") or re.match(r"\s*@\S.*wrote:", q.get_text(" ")):
                    q.decompose()                     # quoted question in a reply
                else:
                    q.insert(0, "“")                  # quoted card text: keep it
                    q.append("”")
            for br in body.find_all("br"):
                br.replace_with("\n")
            leaves = [b for b in body.find_all(["p", "li", "h1", "h2", "h3", "h4", "pre"])
                      if not b.find(["p", "li"])]
            parts = []
            for b in leaves:
                t = b.get_text("", strip=False).strip()
                if b.name == "li":
                    t = "• " + t
                if t:
                    parts.append(t)
            text = "\n".join(parts) if parts else body.get_text("\n", strip=True)
        text = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n") if ln.strip())
        # only rules-team names are kept (the site cites them); askers stay anonymous
        posts.append({
            "id": art.get("id"), "author": author if "RULES" in badges else None, "badges": badges,
            "date": dated["title"] if dated else None,
            "deleted": bool(re.match(r"\[?post deleted", text, re.I)),
            "cards": cards,
            "text": text,
        })
    return {"id": tid, "url": f"{BASE}{SECTION}/{tid}", "title": title.get_text(" ", strip=True) if title else None,
            "posts": posts}


def main():
    ids = thread_ids()
    print(f"{len(ids)} threads")
    threads = []
    for tid in ids:
        th = parse_thread(tid)
        threads.append(th)
        rules = [p["author"] for p in th["posts"] if "RULES" in p["badges"]]
        print(f"  {tid}: {th['title']!r} - {len(th['posts'])} posts, rules team: {rules}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": BASE + SECTION, "fetched": time.strftime("%Y-%m-%d"),
                               "threads": threads}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
