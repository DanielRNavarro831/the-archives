"""Build (and optionally publish) the password-protected playtest site.

    python tools/build_playtest.py             # build into build/playtest-site/ (check it locally)
    python tools/build_playtest.py --publish   # build, then push it to playtest.xwingarchives.com

The playtest site is the staging site plus the real playtest cards and rulings from
data/playtest-private.json (never committed), with:
  - all of its data encrypted with the playtest password (visitors see a password screen),
  - none of staging's made-up test entries (sample playtest cards, test bans, test "outdated" rulings),
  - the Standard / Epic switch, starting in Epic mode; no visitor stats; hidden from search engines.

The password is read from the ARCHIVES_PLAYTEST_PASSWORD environment variable, or the first line of
data/playtest-password.txt (never committed), or asked for. See docs/MAINTAINING.md.
"""
import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_data  # noqa: E402

SITE = ROOT / "site"
BUILD = ROOT / "build"
OUT = BUILD / "playtest-site"
REPO_DIR = BUILD / "playtest-repo"
REPO_URL = "https://github.com/DanielRNavarro831/the-archives-playtest.git"
PRIVATE = ROOT / "data" / "playtest-private.json"
PASSWORD_FILE = ROOT / "data" / "playtest-password.txt"


def git(*args, cwd=ROOT, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr}")
    return r.stdout.strip()


def check_matches_staging(force, publishing):
    """The playtest site must be built from exactly what is on staging."""
    problems = []
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "staging":
        problems.append(f"you're on branch '{branch}', not 'staging'")
    head = git("rev-parse", "HEAD")
    remote = git("ls-remote", "staging", "refs/heads/main").split("\t")[0]
    if remote != head:
        problems.append("this commit isn't what's on the staging site (push to staging first)")
    if git("status", "--porcelain", "--untracked-files=no"):
        problems.append("there are uncommitted changes")
    if problems:
        msg = "The playtest site would not match staging: " + "; ".join(problems) + "."
        if publishing:
            sys.exit(msg + "\nThe playtest site is only published from exactly what's on staging.")
        if not force:
            sys.exit(msg + "\nFix that, or run again with --force to build anyway.")
        print("WARNING: " + msg)
    return head


def password():
    pw = os.environ.get("ARCHIVES_PLAYTEST_PASSWORD")
    if not pw and PASSWORD_FILE.exists():
        lines = PASSWORD_FILE.read_text(encoding="utf-8").strip().splitlines()
        pw = lines[0].strip() if lines else None
    if not pw:
        pw = getpass.getpass("Playtest password: ")
    if len(pw) < 8:
        sys.exit("The playtest password must be at least 8 characters.")
    return pw


def load_site_data():
    s = (SITE / "data" / "archives.js").read_text(encoding="utf-8")
    return json.loads(s[s.index("{"):s.rindex("}") + 1])


def strip_test_entries(d):
    """Remove staging's made-up test data: test bans and test 'outdated' marks."""
    n = 0
    for c in d["cards"]:
        if c.get("bans"):
            keep = [b for b in c["bans"] if not b.get("stagingTest")]
            n += len(c["bans"]) - len(keep)
            if keep:
                c["bans"] = keep
            else:
                del c["bans"]
    for r in d["rulings"]:
        if (r.get("deprecated") or {}).get("stagingTest"):
            del r["deprecated"]
            n += 1
    left = json.dumps(d).count('"stagingTest"')
    if left:
        sys.exit(f"Found {left} other test entries (stagingTest) the playtest build doesn't know how to remove.")
    return n


def build(pw):
    d = load_site_data()
    removed = strip_test_entries(d)
    cards = {c["id"]: c for c in d["cards"]}
    if PRIVATE.exists():
        pt = build_data.load_playtest(cards, PRIVATE)
    else:
        print(f"No {PRIVATE.relative_to(ROOT)} yet: the playtest site will have no playtest cards or rulings.")
        pt = {"cards": [], "rulings": []}
    pt = {k: [x for x in v if not x.get("sample")] for k, v in pt.items()}
    d["playtest"] = pt
    d["meta"]["site"] = "playtest"

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT)
    (OUT / "data" / "archives.js").unlink()
    shutil.copy(ROOT / "tools" / "playtest" / "unlock.js", OUT / "js" / "unlock.js")

    tmp = BUILD / "playtest-data.json"
    tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        subprocess.run(["node", str(ROOT / "tools" / "playtest" / "encrypt.js"), str(tmp),
                        str(OUT / "data" / "archives.locked.js")],
                       env=dict(os.environ, PT_PASSWORD=pw), check=True)
    finally:
        tmp.unlink(missing_ok=True)

    html = (OUT / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'<title>[^<]*</title>', "<title>The Archives — Playtest</title>", html, count=1)
    # no visitor stats on the playtest site
    html = re.sub(r'\s*<!-- Anonymous usage stats.*?</script>', "", html, count=1, flags=re.S)
    old = '<script src="data/archives.js"></script>\n  <script src="js/app.js"></script>'
    if old not in html.replace("\r\n", "\n"):
        sys.exit("index.html changed: couldn't find the data/app script tags to replace.")
    html = html.replace("\r\n", "\n").replace(old, LOCK_HTML)
    html = html.replace("<body>", '<body class="pt-locked">', 1)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    # nothing from the playtest file may appear unencrypted anywhere in the build
    secrets = [x[k] for x in pt["cards"] + pt["rulings"] for k in ("name", "q", "text") if isinstance(x.get(k), str) and len(x[k]) > 6]
    for f in OUT.rglob("*"):
        if f.is_file() and f.suffix in (".html", ".js", ".txt", ".css", ".json"):
            t = f.read_text(encoding="utf-8", errors="ignore")
            leak = next((s for s in secrets if s in t), None)
            if leak:
                sys.exit(f"Playtest text found unencrypted in {f.relative_to(OUT)}: {leak[:60]!r}")
    print(f"Playtest site built in {OUT.relative_to(ROOT)}: {len(pt['cards'])} playtest cards, "
          f"{len(pt['rulings'])} playtest rulings, {removed} staging test entries removed.")


LOCK_HTML = """<style>
    body.pt-locked .topbar nav, body.pt-locked .topsearch, body.pt-locked .footer { visibility: hidden; }
    #pt-lock { max-width: 420px; margin: 12vh auto; padding: 28px 24px; border: 1px solid var(--line, #2a3550);
      border-radius: 12px; background: var(--panel, #131c30); }
    #pt-lock h1 { margin: 0 0 6px; font-size: 1.4rem; }
    #pt-lock p { margin: 0 0 16px; }
    #pt-lock input[type=password] { width: 100%; box-sizing: border-box; padding: 10px 12px; font: inherit;
      border-radius: 8px; border: 1px solid var(--line, #2a3550); background: var(--bg, #0d1424); color: inherit; }
    #pt-lock label.remember { display: flex; gap: 8px; align-items: center; margin: 12px 0 16px; font-size: .95rem; }
    #pt-lock button { padding: 10px 18px; font: inherit; font-weight: 600; border: 0; border-radius: 8px;
      background: var(--accent); color: var(--accent-ink); cursor: pointer; }
    #pt-lock-msg { min-height: 1.4em; margin-top: 12px; }
  </style>
  <section id="pt-lock" hidden>
    <h1>The Archives — Playtest</h1>
    <p class="muted">This site is for the XWA playtest team. Enter the playtest password to continue.</p>
    <form id="pt-lock-form">
      <label for="pt-lock-password" class="muted">Password</label>
      <input type="password" id="pt-lock-password" autocomplete="current-password" required>
      <label class="remember"><input type="checkbox" id="pt-lock-remember"> Remember on this device</label>
      <button type="submit">Unlock</button>
      <p id="pt-lock-msg" class="muted" role="status"></p>
    </form>
  </section>
  <script src="data/archives.locked.js"></script>
  <script src="js/unlock.js"></script>"""


README = """# The Archives — playtest site

Published automatically by `tools/build_playtest.py --publish` from the main Archives repository.
Don't edit this repository by hand: every publish replaces its contents.

The site's data is encrypted; it is unlocked in the browser with the playtest password.
"""


def publish(staging_sha):
    if not REPO_DIR.exists():
        r = subprocess.run(["git", "clone", "-q", REPO_URL, str(REPO_DIR)], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"Couldn't clone {REPO_URL} (has the repository been created?):\n{r.stderr}")
    else:
        git("fetch", "-q", "origin", cwd=REPO_DIR, check=False)
        if git("ls-remote", "origin", "refs/heads/main", cwd=REPO_DIR):
            git("checkout", "-q", "-B", "main", "origin/main", cwd=REPO_DIR)
    for p in REPO_DIR.iterdir():
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    shutil.copytree(OUT, REPO_DIR / "site")
    (REPO_DIR / ".github" / "workflows").mkdir(parents=True)
    shutil.copy(ROOT / ".github" / "workflows" / "pages.yml", REPO_DIR / ".github" / "workflows" / "pages.yml")
    (REPO_DIR / "README.md").write_text(README, encoding="utf-8")
    git("add", "-A", cwd=REPO_DIR)
    if not git("status", "--porcelain", cwd=REPO_DIR):
        print("The playtest site is already up to date.")
        return
    git("commit", "-q", "-m", f"Playtest site from staging {staging_sha[:7]}", cwd=REPO_DIR)
    git("push", "-q", "origin", "HEAD:main", cwd=REPO_DIR)
    print("Pushed to the playtest repository; GitHub Pages publishes it in about a minute.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--publish", action="store_true", help="push the build to playtest.xwingarchives.com")
    ap.add_argument("--force", action="store_true", help="build even if this isn't exactly what's on staging")
    args = ap.parse_args()
    sha = check_matches_staging(args.force, args.publish)
    BUILD.mkdir(exist_ok=True)
    build(password())
    if args.publish:
        publish(sha)


if __name__ == "__main__":
    main()
