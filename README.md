# code2wiki

An Agent Skill that generates a browsable, DeepWiki-style wiki documenting any code repository — its architecture, design, frontend, backend, APIs, data model, and setup — and keeps it up to date.

It runs a four-phase pipeline: **analyze → plan structure → generate pages → build + preview**. On agents that support subagents, page generation fans out across them so the expensive code-reading stays out of the main context; otherwise pages are written sequentially. A manifest file (`wiki.json`) is the contract tying planning, generation, and rendering together.

## Highlights

- **Zero dependencies** — Python standard library only; markdown is rendered client-side (marked.js + mermaid.js + highlight.js), so it runs anywhere Python 3 exists.
- **Portable output** — produces a single self-contained `wiki.html` that opens via `file://` and is trivially shareable. Works fully offline (rendering libraries are inlined; falls back to CDN if unavailable).
- **Live preview** — a local server renders pages straight from disk and auto-reloads the browser as pages are written, so you watch the wiki fill in.
- **Updatable** — revise a page, restructure sections, or refresh after code changes. Per-page provenance front-matter powers staleness detection; `locked: true` shields hand-edited pages from regeneration.

## Screenshots

![Generated wiki landing page](https://github.com/user-attachments/assets/78da5049-fcfa-4f16-9ff4-8291b5166f78)

*A wiki generated for [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) — sidebar navigation, client-side Markdown, and inline Mermaid diagrams. Builds to a single self-contained `wiki.html`.*

## Layout

```
SKILL.md                      # orchestration: the 4 phases + update mode
scripts/
  analyze_repo.py             # repo → analysis.json (tree, languages, deps, entry points, git signal)
  build_site.py               # wiki.json + markdown → self-contained wiki.html
  serve.py                    # live-preview server with auto-reload
assets/
  template.html, style.css, app.js   # the wiki UI (sidebar, search, dark mode, Mermaid)
references/
  section-catalog.md          # which sections to include, by repo type
  page-template.md            # page structure + provenance front-matter rules
```

## Installation

Copy the skill folder into your agent's skills directory. The location varies by
agent — a few common ones:

```bash
# Claude Code — user scope (available in every project)
cp -r . ~/.claude/skills/code2wiki

# Claude Code — project scope (committed, shared with collaborators)
cp -r . <your-repo>/.claude/skills/code2wiki

# Cursor
cp -r . ~/.cursor/skills/code2wiki
```

Check your agent's docs for its skills path; the same folder works across
compatible agents. Then just ask for what you want — the skill triggers on
requests like *"create a wiki for this repo"*, *"document the architecture"*, or
*"explain how this codebase works"*.

## How it works

1. **Analyze** — `analyze_repo.py` emits `analysis.json` (pruned directory tree, language/LOC breakdown, build tools & dependencies, candidate entry points, config files, git hotspots). This gives the planner a cheap, deterministic starting point.
2. **Plan structure** — the agent writes `wiki.json`: sections and pages adapted to what the repo actually contains (a CLI library gets no "Frontend" section; a multi-service repo may get one section per service). The proposed structure is shown to you before generation.
3. **Generate pages** — one page at a time (fanned out across subagents where supported). Each is written from the real code, cites file paths, adds Mermaid diagrams where useful, and lands as its own `.md` file.
4. **Build & preview** — `serve.py` gives a live, auto-reloading preview during generation; `build_site.py` produces the final portable `wiki.html`.

Everything is written under `<repo>/.code2wiki/`:

```
.code2wiki/
  analysis.json
  wiki.json
  content/<section>/<page>.md
  site/wiki.html
```

## Updating an existing wiki

When `.code2wiki/wiki.json` already exists, the skill switches to update mode:

- **Targeted revision** — "improve the Architecture page", "add a page on auth", "split the API page".
- **Refresh after code changes** — re-analyzes, diffs changed source files against each page's recorded `source_files`/`generated_commit`, and regenerates only the stale, unlocked pages.
- **Restructure** — reorganize sections/pages, then rebuild.

## Manual usage of the scripts

The scripts are usable on their own if you want to drive the pipeline by hand:

```bash
# 1. analyze
python3 scripts/analyze_repo.py <repo> --out <repo>/.code2wiki/analysis.json

# 2. (author wiki.json and content/*.md yourself, or let the skill do it)

# 3a. live preview
python3 scripts/serve.py --wiki-dir <repo>/.code2wiki --assets-dir ./assets --port 8000

# 3b. static build  (add --cdn to link libraries instead of inlining them)
python3 scripts/build_site.py --wiki-dir <repo>/.code2wiki --assets-dir ./assets \
    --out <repo>/.code2wiki/site/wiki.html
```

## Requirements

- Python 3.8+
- A modern web browser to view the output
- Internet access on the **first** static build (to fetch the rendering libraries, which are then cached in `assets/vendor/`); not required afterward
