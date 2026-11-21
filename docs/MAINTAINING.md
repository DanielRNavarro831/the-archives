# Maintaining The Archives

The website never reads the PDFs directly. A two-step pipeline turns them into
`site/data/archives.js`, which the site loads.

```
PDF ──(tools/extract_pdf.py)──> data/raw/*.json ──┐
                                                   ├─(tools/build_data.py)──> site/data/archives.js
YASB ──(fetch_yasb.py, import_yasb.js)──> data/yasb/yasb-cards.json ──┘
```

- **Rulings, errata, rules** come from the XWA PDFs.
- **Card text, stats and dials** come from YASB (points and upgrade bars are left out on purpose, since they change with points updates) (https://yasb.app,
  source at github.com/raithos/xwing, MIT License). Every pilot and upgrade has a page,
  and the PDF rulings attach to the matching card.

One-time setup (already done on this computer): Python 3, Node.js,
`python -m pip install pymupdf`, and `npm install` inside the `tools` folder.

## Refreshing card data from YASB (e.g. after an XWA card text update)

```powershell
python tools/fetch_yasb.py
```

```powershell
node tools/import_yasb.js
```

```powershell
python tools/build_data.py
```

The last command prints how many PDF cards matched a YASB card. The full list of matches
is in `data/yasb/match-report.json`. If a ruling lands on the wrong card, or a card stops
matching after a rename, add a line to `yasbMatch` in `data/cards-curated.json`, e.g.
`"slave-i-title": "slave-i-title"` (PDF card id → YASB card id), or `null` to leave the PDF card on its own.

This also fixes cards a document **misnames**. For example, the FAQ says "Admiral Holdo", so
`"admiral-holdo-crew": "amilyn-holdo-crew"` points it at the real card. The ruling keeps the FAQ's wording, but the
wrong name becomes an alias: it links to the real card and search finds it. A card with no text and no
stats on the site is usually one of these.

## Updating to a new version of a document

1. Put the new PDF in the `pdfs/` folder (e.g. `rules-reference-v1.5.0.pdf`). This folder is **not** published; the site only cites the documents.
2. Extract its text:

   ```powershell
   python tools/extract_pdf.py pdfs/rules-reference-v1.5.0.pdf data/raw/rules-reference-v1.5.0.json
   ```

3. Edit `data/sources.json`: update `version`, `effective`, `file` and `raw`.
   **Check the page ranges** in `sections` against the new PDF (e.g. if the FAQ now
   starts on page 35, change `"from": 34`). This is the step most likely to need attention.
4. Extract the example pictures (diagrams, card examples) from the new PDF:

   ```powershell
   python tools/extract_figures.py pdfs/rules-reference-v1.5.0.pdf rr
   ```

   This saves them to `site/figures/` and records where each one sits on its page. The build
   step puts each picture after the paragraph it follows in the PDF. If one lands in the wrong
   rule, add it to `data/figures-curated.json` (`"rr-p29-3.webp": "device-and-deploying-examples"`).

5. Rebuild the database:

   ```powershell
   python tools/build_data.py
   ```

   It prints counts like `rules=276 rulings=112 errata=73 cards=188 unmatched=0`.
   If `unmatched` is above 0, open `data/unmatched-mentions.json` to see which card
   mentions it couldn't understand.
6. Open the site and spot-check a few new rulings and pictures against the PDF.

## Fixing card detection (`data/cards-curated.json`)

Cards are found automatically from:
- errata entries ("•Fenn Rau (Rebel, Sheathipede-class Shuttle) Should read…"), and
- bracketed mentions in rulings ("Han Solo [Rebel, {gunner}]", "Elusive [{talent}]").

The curated file handles everything else:

| Key | Use it when… | Example |
| --- | --- | --- |
| `cards` | A card is mentioned **without** brackets (e.g. "Seasoned Navigator"), or you want to set its name/type/ship/faction precisely. Add `"plain": true` for one-word names like "Fearless". Add `"text"` to give a card its full text. | `{"id": "snap-shot-talent", "name": "Snap Shot", "type": "Upgrade", "slot": ["Talent"]}` |
| `mentionIds` | Two different spellings should be the same card, or a name should point to a specific card. | `"Paige Tico [{crew}]": "paige-tico-gunner"` |
| `ignore` | Something in brackets isn't a card. | `"Mine [and overlaps]"` |
| `errataSlots` | An errata'd upgrade doesn't state its slot. | `"Composure": "Talent"` |
| `shipAliases` | The document misspells a ship. | `"TIE/ba Inteceptor": "TIE/ba Interceptor"` |
| `rulingCards` / `rulingCardsRemove` | Manually attach/detach a card to/from a ruling by ruling id (shown in the URL, e.g. `#/ruling/rr-52`). | `"rr-52": ["iden-versio-tie-ln-fighter"]` |

Card ids are `name-ship` for pilots and `name-slot` for upgrades, all lowercase with dashes.
After any change, run `python tools/build_data.py` again.

## Changing the look

Colours and fonts are CSS variables at the top of `site/css/style.css`
(`--accent` is the amber highlight colour). The light theme overrides are just below.

## Site settings (`data/sources.json`)

- `documentsPage`: paste the XWA's official documents download page here. Every
  "Rules Reference v1.4.6, p. 37" citation will then link to it. While it's empty, citations are plain text.
- `reportForm`: the Google Form behind every **Report a Problem or Ruling** link.
  `field` is the id of the form question that gets pre-filled with the card/ruling and page
  the reader was looking at. If you replace the form, get the new id from the form's
  "Get pre-filled link" option (it looks like `entry.123456789`).

After changing either, run `python tools/build_data.py`.

## Icons and fonts

- Icons use the **X-Wing Miniatures Font** (`site/fonts/xwing-miniatures.ttf`) and ship
  silhouettes use `xwing-miniatures-ships.ttf`. Both are SIL Open Font License, fine to publish.
- Which character is which icon lives in `site/js/icons.js`, generated from
  `data/icons/xwing-miniatures.css` by `python tools/build_icons.py`. If you get a newer
  font version, replace both files and re-run that script.
- Resistance uses the font's outlined starbird (`rebel-outline`). Hyperdrive and Mission Point
  have no icon in the font and fall back to text labels.
- **Heading font:** one line in `site/css/style.css` (`--font-head`) controls it. The chosen
  heading font is Bank Gothic. Bank Gothic, Eurostile, Kimberley and Star Jedi are commercial or
  differently licensed fonts: check that you have a **web** license before publishing them.

## Rulings from the XWA rules forum

Answers from the XWA rules team on https://www.xwing.life/forum/rules-questions are
imported as rulings. Only replies with the **RULES** badge count; placeholders like
"we'll answer soon" and deleted posts are skipped. **Maui is the XWA rules lead**: his
answers are shown first and marked "XWA Rules Lead".

To pick up new answers:

```powershell
python tools/fetch_forum.py
```

```powershell
python tools/build_data.py
```

`data/forum/match-report.json` lists which cards each answer was attached to. Fix any
mistakes in `data/forum-curated.json` (`addCards` / `removeCards` per thread number, or
`skipThreads` to leave a thread out), then run `python tools/build_data.py` again.

## The Compendium (numbered reference)

`python tools/build_data.py` also builds the Compendium: the Rules Reference glossary and
appendices, FAQ, forum answers and errata in one document, one numbered section per topic.
Every paragraph gets a reference like **§22.4** (section 22, paragraph 4). The site shows it
under **Compendium**, and `site/compendium.txt` is the same thing as plain text.

- Rulings are placed under a topic automatically: FAQ headings first (e.g. "Locking" → Lock),
  otherwise the most specific glossary term the question uses.
  `data/compendium-report.json` shows where each ruling went and why.
- To move a ruling, add it to `data/compendium-curated.json`, e.g. `"rr-66": "Attack"`.
- Numbers can shift when a new Rules Reference adds entries, so cite them with the edition.

**Using it with an AI assistant without made-up rulings:** give it `compendium.txt` and ask
it to answer *only* with § numbers, then look those numbers up on the site ("Go to §" box,
or type §22.4 in the search box) and read the actual text yourself.

## Official PDF links and the Epic switch (`data/sources.json`)

- Every rules citation ("Rules Reference v1.4.6, p. 37") links to the **XWA's official PDF**
  at that page, using each document's `url`. The PDFs are not hosted here. When the XWA
  publishes a new version, update that document's `version` and `url` (the new file's address
  on https://www.xwing.life/rules) along with the local copy used for extraction.
- **Standard / Epic mode.** Epic content is kept in the data but flagged "epic", and only shows
  in **Epic mode**. It covers documents marked `"epic": true` (the Epic Battles Rules Reference),
  plus the Rules Reference's Appendix: Huge Ships and Huge Ship FAQ, forum thread 66, and the
  Stalwart Captain and CR90 dial errata (listed under `"epic"`).
  - `"epicToggle"` decides where the **Standard | Epic** switch appears in the header:
    `"staging"` (staging only), `"live"` (both sites) or `null` (nowhere). Without the
    switch, the site is Standard only. Each visitor's choice is remembered in their browser.
  - In Epic mode, a purple bar says so, everything Epic gets a purple **Epic** tag, and
    Standard rules that the Epic rules also define (e.g. Setup) point to the Epic version.
    "See X" links go to the Epic rule. The Compendium and Judge Quiz stay Standard only.
  - An Epic link opened in Standard mode shows a "This is an Epic rule" page with a switch button.
  - `"hideEpic": true` keeps the About page's note that Epic content is not shown yet.
  - **Updating the Epic rules:** add the new PDF like any document (see below), with
    `"epic": true` and its `sections`. A section can start partway through a page with
    `"startText"` (the first words of its first paragraph), e.g. the Epic FAQ and Event Guidance
    share page 8. Epic rules get addresses like `#/rule/epic-wings`.
    Diagrams: `python tools/extract_figures.py pdfs/<epic pdf> ep`. Fix-ups live in
    `data/figures-curated.json`: `dropFigure` (not a real diagram), `figureBox` (re-crop in PDF points),
    `placeFigure` (move to another rule) and `dropLabel` (picture labels that leaked into the text).
  - **Official XWA Epic Rules (Beta 2.1)** is document `xe`. It's a single-column PDF from a word
    processor, so it uses its own reader:
    `python tools/extract_doc_pdf.py pdfs/<file>.pdf data/raw/<raw>.json --promote "Additional Rules"`
    (headings are found by font size; `--promote` makes the sub-headings under "Additional Rules"
    entries of their own). Its rules get addresses like `#/rule/xwa-epic-wings`
    (`"idPrefix"`), and names used in two parts get the part added, e.g. "Squad Building (Wings)"
    (`"dedupeTitles"`).
  - **Outdated rules:** like rulings, rules entries can be marked outdated in
    `data/deprecated-rulings.json`, under `"rules"` (same fields; `replacedBy` is a rule id).
    Beta 2.1 replaced the Rules Reference's Appendix: Huge Ships and the wing rules, allied,
    command upgrades and restore entries of Epic v1.0.6. Those are kept, marked Outdated, and
    link to their replacement.

## Usage statistics (GoatCounter)

Anonymous stats are at **https://xwingarchives.goatcounter.com** (log in to view). The site sends:

- a page view for each page opened: `/card/<id>`, `/rule/<id>`, `/s/<section>`, `/faq`, …
  (an exact-name search that jumps straight to a card counts as a view of that card);
- an event for each search: `search: <what was typed>`, or `search (no results): <text>` when
  nothing matched, which is the most useful list for spotting what people can't find.

No cookies or personal data; GoatCounter reports countries. Visits from `localhost` aren't counted.
The script in `site/index.html` is pinned to a fixed version with an integrity hash; if GoatCounter
ever stops loading, that pin is the first thing to check. The tracking code is the
"anonymous usage stats" block in `site/js/app.js`. Remove both to turn stats off.

## Staging: test changes before they go live

| | Live | Staging |
|---|---|---|
| Address | https://xwingarchives.com | https://staging.xwingarchives.com |
| GitHub repository | `the-archives` | `the-archives-staging` |
| Git branch (in this folder) | `main` | `staging` |
| Usage stats | on | **off** |
| Search engines | soft launch: blocked | **always blocked** |
| Banner | none | orange **STAGING** banner |

Both sites are built from this same folder; there is only one copy of the code.

**Day-to-day:**

1. Work on the `staging` branch: `git switch staging`
2. Publish to staging (only the staging site changes):

   ```powershell
   git push staging staging:main
   ```

3. Check it at https://staging.xwingarchives.com (share that link with testers if you like).
4. When it's approved, put the same changes live:

   ```powershell
   git switch main
   ```
   ```powershell
   git merge staging
   ```
   ```powershell
   git push origin main
   ```

The staging copy decides it is staging purely from its address (`staging.…`), so the same files
behave correctly on both sites. "Report a Problem" submissions from staging start with
`[STAGING SITE]` in the Google Form.

**If a GitHub site's HTTPS certificate never arrives** (Settings → Pages shows no certificate
after an hour), remove the custom domain in Settings → Pages, save, add it back, and re-run the
"Publish site" workflow. That restarted the stuck certificate for the staging site.

## Outdated (deprecated) rulings

When a new document changes or removes a ruling, you can keep the old one visible for
reference instead of deleting it. Add it to `data/deprecated-rulings.json`:

```json
"rr-50": { "asOf": "Rules Reference v1.4.7", "reason": "Optional short explanation.", "replacedBy": "rr-123" }
```

- The ruling gets a red outline and an **Outdated** label ("No longer current as of …").
- Its citation becomes plain text ("Originally: …"), since that PDF version may no longer be online.
- On card pages it's listed after the current rulings; search results and the plain-text
  Compendium label it as outdated. `replacedBy` (optional) adds a link to the new ruling.
- `"stagingTest": true` makes an entry show **only on staging**, for trying things out.
  Never use it on a real deprecation.

Then run `python tools/build_data.py`.

## Banned cards

List bans in `data/banned-cards.json`, one list per card (a card can be banned in more than one format):

```json
"ion-cannon-battery-hardpoint": [
  { "format": "Epic", "where": "all" },
  { "format": "Epic", "where": ["Scenario name", "Another scenario"], "since": "Epic Rules v1.0", "note": "Optional." }
]
```

- `"where": "all"` shows **"Banned in all scenarios"**; a list shows **"Banned in: …"** with those scenarios.
- The card page gets a red **BANNED** notice at the top; card lists and search suggestions show a
  "Banned" tag, and the Cards page filter gains a **Banned** option (only when something is banned).
- `"stagingTest": true` makes a ban show **only on staging**. The two current entries are tests.

Then run `python tools/build_data.py`.

## Playtest cards and rulings (experimental)

`data/playtest.json` holds upcoming cards and rulings. They are kept apart from the official data
(never in the Compendium or the Judge Quiz) and only appear in **playtest mode**, tagged with a
green **Playtest** label under a green "subject to change" banner:

- on `playtest.xwingarchives.com` (not set up yet; no stats, hidden from search engines), and
- on staging, as a preview: click **Preview the playtest site** in the orange banner (adds `?playtest` to the address).

Entries with `"sample": true` are made-up examples that only show in the staging preview.
A new pilot can copy its ship, stats, actions and dial from an existing pilot with `"base": "<card id>"`.
Run `python tools/build_data.py` after editing.

**Important:** anything in `data/playtest.json` is published inside `site/data/archives.js` and the
repositories are public, so real playtest content must not go in here until the playtest site has
its own private setup with access control.

## Judge Quiz

`#/quiz` asks 10 random **Yes / No** questions. Each one is an official ruling (Rules Reference FAQ or
XWA rules-team forum answer) whose official answer starts with "Yes" or "No", used word for word;
after each answer the official answer and citation are shown. Outdated rulings and questions that
ask two things at once are left out. Nothing is stored and nothing is typed.
To keep a confusing ruling out of the quiz (it stays on the site as written), add its id to
`quizSkip` in `data/sources.json`, e.g. `"quizSkip": ["forum-32"]`, then rebuild.

It is **live** (`"quizLive": true` in `data/sources.json`). To hide it on the live site, set
`quizLive` to `false`, run `python tools/build_data.py`, then publish (it always shows on staging). To remove it entirely, delete the
"Judge Quiz" block from `site/js/app.js` and the quiz styles from `site/css/style.css`.

## Unprinted cards

`data/unprinted-cards.json` holds upgrades that exist only as text in a rules document, such as the
Epic command upgrades (Wing Leader, Wingmate, Commander, Wing Guard). Each one has the card's text
word for word, its slot, restriction, the document and page it comes from, and the rule that explains it.
Cards with `"epic": true` only show in Epic mode. The build warns when a card's text is no longer in its
document, so after a new version of the document, fix the text here. Never add points or loadout values.

## Rulings that may also apply

A ruling is tied to the cards it names. `data/related-rulings.json` adds reviewed links to other cards
whose text uses the same mechanic: they show on the card page under "Rulings that may also apply", with a
note that the ruling doesn't name that card. Only groups with `"status": "approved"` are shown;
`"rejected"` groups are kept so they aren't suggested again. After editing the file, run
`python tools/build_data.py`, then `python tools/related_review.py` to refresh the review checklist in
`docs/related-rulings-review.md`.
