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

## Updating to a new version of a document

1. Put the new PDF in the `pdfs/` folder (e.g. `rules-reference-v1.5.0.pdf`). This folder is **not** published; the site only cites the documents.
2. Extract its text:

   ```powershell
   python tools/extract_pdf.py pdfs/rules-reference-v1.5.0.pdf data/raw/rules-reference-v1.5.0.json
   ```

3. Edit `data/sources.json`: update `version`, `effective`, `file` and `raw`.
   **Check the page ranges** in `sections` against the new PDF (e.g. if the FAQ now
   starts on page 35, change `"from": 34`). This is the step most likely to need attention.
4. Rebuild the database:

   ```powershell
   python tools/build_data.py
   ```

   It prints counts like `rules=276 rulings=112 errata=73 cards=188 unmatched=0`.
   If `unmatched` is above 0, open `data/unmatched-mentions.json` to see which card
   mentions it couldn't understand.
5. Open the site and spot-check a few new rulings against the PDF.

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
