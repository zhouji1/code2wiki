---
name: code2wiki
description: >-
  Generate a browsable, DeepWiki-style wiki that documents a code repository —
  its architecture, design, frontend, backend, APIs, data model, and setup.
  Use this whenever the user wants to understand, document, explain, or onboard
  onto a codebase: e.g. "create a wiki for this repo", "document the architecture",
  "generate docs for this project", "explain how this codebase works", "make a
  deepwiki", "build a knowledge base for our code". Also use it to UPDATE an
  existing generated wiki — add or revise a page, restructure sections, or
  refresh pages after code changes. Trigger even when the user doesn't say the
  word "wiki" but clearly wants structured, navigable documentation of a repo.
---

# code2wiki

Generate a browsable wiki that explains a code repository, then update it on request.

The pipeline has four phases: **analyze → plan structure → generate pages → build + preview**. When the agent supports subagents, generate pages with them so the heavy code-reading stays out of the main context; otherwise write the pages sequentially yourself. A manifest file (`wiki.json`) is the contract tying planning, generation, and rendering together.

The bundled scripts use only the Python standard library, and the wiki renders in the browser with no build toolchain — so this skill runs on any Agent Skills-compatible agent that can execute shell commands and read/write files.

Everything is written under `<repo>/.code2wiki/` (add it to `.gitignore` unless the user wants it committed):

```
.code2wiki/
  analysis.json          # output of analyze_repo.py
  wiki.json              # the structure manifest (sections + pages)
  content/<section>/<page>.md   # generated markdown, one file per page
  site/wiki.html         # self-contained static build (portable, file://-openable)
```

## Decide the mode first

Look at the repo and the user's request:

- **No `.code2wiki/wiki.json` exists** → this is a **fresh generation**. Run all four phases.
- **`wiki.json` already exists** → this is an **update**. Jump to the "Updating an existing wiki" section.

Confirm the target repo path with the user if it's ambiguous (default: the current working directory).

---

## Phase 1 — Analyze the repository

Run the analyzer to get a structured snapshot cheaply and deterministically:

```bash
python3 <skill-dir>/scripts/analyze_repo.py <repo-path> --out <repo>/.code2wiki/analysis.json
```

This emits `analysis.json` with: pruned directory tree, language/LOC breakdown, detected build tools & dependencies (package.json, requirements.txt, go.mod, pom.xml, Cargo.toml, …), candidate entry points, config files, and git signal (most-changed files, recent activity, contributors).

**Ignored files are excluded.** If the repo has a `.gitignore`, any path it matches is skipped — both in the directory tree and the language/LOC/dependency stats — so generated output, vendored code, and secrets don't pollute the analysis or leak into the wiki. Nested `.gitignore` files are honored and scoped to their own directory, and `!` re-includes work. `analysis.json` reports `gitignore_respected: true` when patterns were applied. Pass `--no-gitignore` to analyze every file regardless. This is on by default — no extra step needed.

Then **read the key files yourself** to form an architectural mental model — at minimum the README, the top entry points, and the main config/build files that `analysis.json` surfaced. Don't read the whole repo; you're orienting, not documenting. The goal is to know enough to plan a good structure and to write precise `hints` for each page.

## Phase 2 — Plan the wiki structure

Write `<repo>/.code2wiki/wiki.json` describing the sections and pages. **Adapt the structure to what actually exists** — a CLI library shouldn't have a "Frontend" section; a microservice repo might need one section per service. See `references/section-catalog.md` for the candidate sections and when each is worth including.

Schema:

```json
{
  "title": "<repo-name> Wiki",
  "repo": "<absolute repo path>",
  "generated_at": "<today's date>",
  "generated_with": "<LLM provider and model, e.g. 'Anthropic Claude Opus 4.8'>",
  "sections": [
    {
      "id": "overview",
      "title": "Overview",
      "pages": [
        {
          "id": "introduction",
          "title": "Introduction",
          "file": "content/overview/introduction.md",
          "hints": "What the project does, who it's for, key capabilities. Lead from README.md and package.json.",
          "source_files": ["README.md", "package.json"]
        }
      ]
    }
  ]
}
```

`hints` and `source_files` are the brief you hand to the page writer — make them specific (name real files from `analysis.json`). `id`s must be filesystem-safe (lowercase, hyphens). Set `generated_with` to the provider and model you (the generating LLM) are running as, e.g. `"Anthropic Claude Opus 4.8"`.

Briefly print the proposed structure (just the section/page titles) so the user can see what's coming, then **continue straight into Phase 3 — do not stop to ask for confirmation**. The user can always interrupt to adjust, and revising the manifest later is cheap. Only pause here if the user explicitly asked to review the structure first.

## Phase 3 — Generate the pages

Write the markdown **one page at a time** using the brief below. The order doesn't matter; pick whichever approach your agent supports:

- **With subagents (preferred):** dispatch one subagent per page in parallel batches — about 4–6 in flight for a medium repo. Each subagent reads the real code, writes its file directly, and returns only a done/failed status, keeping the main context clean.
- **Without subagents:** write each page yourself, sequentially, following the same brief.

Either way, apply **adaptive batching**: **merge** trivially small pages into a sibling, and **split** a page whose scope is clearly too big into two manifest entries before writing.

Brief for each page (fill in the brackets):

```
You are writing ONE page of a repository wiki. Read the real code — do not guess.

Repo: <repo path>
Page: <page title>  (section: <section title>)
Write the markdown to: <repo>/.code2wiki/<page.file>
What this page must cover: <page.hints>
Start from these files: <page.source_files>
Analysis snapshot: <repo>/.code2wiki/analysis.json  (read for tree/deps/entry points)

Follow the page template and rules in:
  <skill-dir>/references/page-template.md

Key rules: cite real file paths (as `path/to/file.ts:42`), include a Mermaid
diagram when it aids understanding (```mermaid fenced block), keep claims
grounded in code you actually read, and begin the file with the YAML
front-matter block specified in the template.
```

When the pages are written, verify each expected file exists and is non-trivial. Regenerate any that failed.

## Phase 4 — Build and preview

**Live preview while generating** (optional but useful — start it during Phase 3 to watch pages fill in):

```bash
python3 <skill-dir>/scripts/serve.py --wiki-dir <repo>/.code2wiki --assets-dir <skill-dir>/assets --port 8000
```

This serves the same wiki UI but reads the markdown live from disk; it auto-reloads the browser when files change. Tell the user the URL (http://localhost:8000) and that it updates as pages are written.

**Static build** (the portable deliverable):

```bash
python3 <skill-dir>/scripts/build_site.py --wiki-dir <repo>/.code2wiki --assets-dir <skill-dir>/assets --out <repo>/.code2wiki/site/wiki.html
```

This produces a single self-contained `wiki.html` (all markdown + nav + rendering libs inlined) that opens directly via `file://` and is trivially shareable. Add `--cdn` to link rendering libraries from a CDN instead of inlining them (smaller file, needs internet to view). Report the output path to the user.

---

## Updating an existing wiki

When `wiki.json` exists, figure out which of three update kinds the user wants:

**1. Targeted revision** — "improve the Architecture page", "add a page on auth under Backend", "split the API page".
- For a content rewrite: regenerate that page (same brief as Phase 3) and overwrite its `.md`.
- For structural changes: edit `wiki.json` (add/remove/reorder entries), then generate any new pages.
- Respect `locked: true` front-matter — skip regenerating locked pages unless the user explicitly targets them.

**2. Refresh after code changes** — "update the wiki, the code changed".
- Re-run `analyze_repo.py`.
- Find changed source files: `git -C <repo> diff --name-only <generated_commit>..HEAD` (the commit is recorded in each page's front-matter), or diff the new `analysis.json` against the old.
- A page is **stale** if any of its `source_files` changed. Regenerate only stale, unlocked pages. Report what was refreshed and what was skipped.

**3. Restructure** — reorganize sections/pages. Edit `wiki.json`, regenerate affected pages, rebuild.

Always finish an update by re-running the static build (Phase 4) and reporting what changed.

### Provenance front-matter

Every generated page begins with this block (the page template enforces it). It powers staleness detection and protects manual edits:

```yaml
---
title: Architecture Overview
source_files: [src/server.ts, src/router.ts]
generated_at: 2026-05-28
generated_commit: a1b2c3d
locked: false
---
```

Set `locked: true` on a page (or tell the user they can) to shield hand-edited wording from future refreshes.

---

## Reference files

- `references/section-catalog.md` — candidate wiki sections/pages and when to include each. Read during Phase 2.
- `references/page-template.md` — the structure and rules each page must follow. Read this (or have the page-writing subagent read it) in Phase 3.

## Notes

- `<skill-dir>` is this skill's directory. The scripts use only the Python standard library — no `pip install` needed.
- Keep `analysis.json` and `wiki.json` as the source of truth; the static build is regenerable output.
