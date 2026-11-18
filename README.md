# The Archives

A rules lookup website for *Star Wars: X-Wing*, in the spirit of Magic's Gatherer:
search a pilot or upgrade and see every official ruling and erratum that applies to it.
All content comes from the X-Wing Alliance (XWA) rules documents.

## Look at the site on your computer

The site is plain HTML, CSS and JavaScript. Nothing needs to be installed to view it.

- **Quickest:** double-click `site/index.html`. It opens in your browser.
- **Like a real web server** (recommended while editing): open PowerShell in this folder and run

  ```powershell
  python -m http.server 8765 --directory site
  ```

  then visit http://localhost:8765. Press `Ctrl+C` in PowerShell to stop it.

## What's in this folder

| Path | What it is |
| --- | --- |
| `site/` | **The website.** This whole folder is what gets published. |
| `site/index.html` | The page skeleton (header, footer). |
| `site/css/style.css` | All colours, fonts and layout. Colours are at the top. |
| `site/js/app.js` | The site logic: search, card pages, rules, FAQ, errata. |
| `site/data/archives.js` | The database. **Generated, don't edit by hand.** |
| `pdfs/` | The official PDFs, used only by the build tools. **Not published.** |
| `data/sources.json` | Which PDF is which version, and which pages hold which section. |
| `data/cards-curated.json` | Hand-made fixes for card detection (see `docs/MAINTAINING.md`). |
| `data/raw/` | Text pulled out of the PDFs (step 1 output). |
| `tools/` | Scripts that turn the PDFs and the YASB card data into the database. |
| `data/yasb/` | Card data from YASB (text, stats, dials). Points and upgrade bars are intentionally not imported. |

## When the XWA publishes a new document

See [docs/MAINTAINING.md](docs/MAINTAINING.md) for the step-by-step.

## The live site

**https://danielrnavarro831.github.io/the-archives/**

GitHub Pages publishes the `site/` folder automatically every time `main` is pushed
(see `.github/workflows/pages.yml`). Changes are live a minute or two after a push.

- **Soft launch mode:** search engines are asked not to list the site (`site/robots.txt`
  and the `robots` line in `site/index.html`). Delete both at the public launch.
- **To take it offline:** on GitHub open the repo's **Settings → Pages** and choose
  **Unpublish site** (or make the repository private again in **Settings → General**).
  You can publish it again later without losing anything.
- **Custom domain (later):** buy the domain, then enter it in **Settings → Pages → Custom domain**
  and follow GitHub's DNS instructions. HTTPS is set up automatically.

## Disclaimer

Unofficial and fan-made. Star Wars: X-Wing is © & ™ Lucasfilm Ltd. Not affiliated with
Lucasfilm, Disney, or Atomic Mass Games. The official documents are always authoritative.

## Working from a fresh copy of this repository

- The official PDFs are **not** in the repository. To re-extract rules after a new XWA
  document comes out, put the PDFs in a `pdfs/` folder (see `data/sources.json` for the file names).
- Install the tools once: `python -m pip install pymupdf beautifulsoup4`, then `npm install` inside `tools/`.
