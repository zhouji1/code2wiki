#!/usr/bin/env python3
"""Build a self-contained static HTML wiki from a wiki.json manifest + markdown.

Standard library only. Produces a single portable HTML file with the manifest,
all page markdown, and the rendering libraries inlined — it opens directly via
file:// and is trivially shareable. Use --cdn to link the rendering libraries
from a CDN instead (smaller file, but needs internet to view).

Usage:
  python3 build_site.py --wiki-dir <dir> --assets-dir <skill>/assets \
      --out <dir>/site/wiki.html [--cdn]
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# (filename, url, kind). Downloaded and inlined for the offline build.
VENDOR = [
    ("marked.min.js", "https://cdn.jsdelivr.net/npm/marked@12/marked.min.js", "js"),
    ("mermaid.min.js", "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js", "js"),
    ("highlight.min.js", "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11/highlight.min.js", "js"),
    ("github.min.css", "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11/styles/github.min.css", "css"),
]


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "code2wiki-build"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def cache_vendor(assets_dir: Path) -> dict:
    """Ensure vendor files exist in assets/vendor/, downloading if missing.
    Returns {filename: text or None}. None means download failed (use CDN)."""
    vendor_dir = assets_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, url, _kind in VENDOR:
        local = vendor_dir / name
        if local.exists() and local.stat().st_size > 0:
            out[name] = local.read_text(encoding="utf-8", errors="replace")
            continue
        try:
            text = fetch(url)
            local.write_text(text, encoding="utf-8")
            out[name] = text
            print(f"  downloaded {name}")
        except Exception as e:  # offline or blocked — fall back to CDN link
            print(f"  could not download {name} ({e}); will use CDN link")
            out[name] = None
    return out


def js_safe_json(obj) -> str:
    """JSON safe to embed inside a <script> tag."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def collect_content(wiki_dir: Path, manifest: dict) -> dict:
    content = {}
    missing = []
    wiki_root = wiki_dir.resolve()
    for section in manifest.get("sections", []):
        for page in section.get("pages", []):
            rel = page.get("file")
            if not rel:
                continue
            fp = (wiki_dir / rel).resolve()
            try:
                fp.relative_to(wiki_root)  # keep manifest paths inside the wiki dir
            except ValueError:
                print(f"  warning: skipping page outside wiki dir: {rel}", file=sys.stderr)
                continue
            if fp.is_file():
                content[rel] = fp.read_text(encoding="utf-8", errors="replace")
            else:
                content[rel] = f"# {page.get('title','(missing)')}\n\n_This page has not been generated yet._"
                missing.append(rel)
    return content, missing


def vendor_scripts_block(vendor: dict, cdn: bool) -> str:
    parts = []
    for name, url, kind in VENDOR:
        text = vendor.get(name)
        if cdn or text is None:
            if kind == "js":
                parts.append(f'<script src="{url}"></script>')
            else:
                parts.append(f'<link rel="stylesheet" href="{url}">')
        else:
            if kind == "js":
                parts.append("<script>" + text + "</script>")
            else:
                parts.append("<style>" + text + "</style>")
    return "\n  ".join(parts)


def build(wiki_dir: Path, assets_dir: Path, out: Path, cdn: bool):
    manifest_path = wiki_dir / "wiki.json"
    if not manifest_path.exists():
        print(f"error: {manifest_path} not found", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    template = (assets_dir / "template.html").read_text(encoding="utf-8")
    style = (assets_dir / "style.css").read_text(encoding="utf-8")
    app_js = (assets_dir / "app.js").read_text(encoding="utf-8")

    print("Preparing rendering libraries…")
    vendor = {} if cdn else cache_vendor(assets_dir)
    if cdn:  # still need URLs; cache_vendor not called
        vendor = {name: None for name, _u, _k in VENDOR}

    content, missing = collect_content(wiki_dir, manifest)

    data_block = (
        "<script>window.WIKI_DATA="
        + js_safe_json(manifest)
        + ";window.WIKI_CONTENT="
        + js_safe_json(content)
        + ";</script>"
    )

    html = (
        template
        .replace("__WIKI_TITLE__", manifest.get("title", "Wiki"))
        .replace("<!-- __HEAD_EXTRA__ -->", "")
        .replace("__STYLE__", style)
        .replace("__VENDOR_SCRIPTS__", vendor_scripts_block(vendor, cdn))
        .replace("__WIKI_DATA__", data_block)
        .replace("__APP_JS__", app_js)
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    pages = sum(len(s.get("pages", [])) for s in manifest.get("sections", []))
    print(f"\nBuilt {out}")
    print(f"  {len(manifest.get('sections', []))} sections, {pages} pages, "
          f"{out.stat().st_size // 1024} KB")
    if missing:
        print(f"  warning: {len(missing)} page(s) not yet generated: "
              + ", ".join(missing[:5]) + ("…" if len(missing) > 5 else ""))
    print(f"\n  Open it: file://{out.resolve()}")


def main():
    ap = argparse.ArgumentParser(description="Build a self-contained static wiki HTML.")
    ap.add_argument("--wiki-dir", required=True, help="dir containing wiki.json and content/")
    ap.add_argument("--assets-dir", required=True, help="skill assets dir (template/style/app/vendor)")
    ap.add_argument("--out", required=True, help="output HTML path")
    ap.add_argument("--cdn", action="store_true", help="link libraries from CDN instead of inlining")
    args = ap.parse_args()

    build(
        Path(args.wiki_dir).expanduser().resolve(),
        Path(args.assets_dir).expanduser().resolve(),
        Path(args.out).expanduser(),
        args.cdn,
    )


if __name__ == "__main__":
    main()
