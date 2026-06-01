#!/usr/bin/env python3
"""Live-preview server for a code2wiki wiki.

Standard library only. Serves the same wiki UI as the static build, but reads
wiki.json and the page markdown live from disk on each request, and exposes a
/__mtime endpoint the page polls to auto-reload when files change. Run this
during page generation to watch the wiki fill in.

Usage:
  python3 serve.py --wiki-dir <dir> --assets-dir <skill>/assets [--port 8000]
"""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Reuse the vendor list/URLs from build_site so the two stay in sync.
VENDOR = [
    ("marked.min.js", "https://cdn.jsdelivr.net/npm/marked@12/marked.min.js", "js"),
    ("mermaid.min.js", "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js", "js"),
    ("highlight.min.js", "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11/highlight.min.js", "js"),
    ("github.min.css", "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11/styles/github.min.css", "css"),
]

CONTENT_TYPES = {
    ".js": "application/javascript", ".css": "text/css", ".json": "application/json",
    ".md": "text/markdown; charset=utf-8", ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png",
}


def vendor_scripts_block(assets_dir: Path) -> str:
    """Prefer locally-vendored files (offline); otherwise link the CDN."""
    vendor_dir = assets_dir / "vendor"
    parts = []
    for name, url, kind in VENDOR:
        local = vendor_dir / name
        src = "/vendor/" + name if local.exists() and local.stat().st_size > 0 else url
        if kind == "js":
            parts.append(f'<script src="{src}"></script>')
        else:
            parts.append(f'<link rel="stylesheet" href="{src}">')
    return "\n  ".join(parts)


def render_index(assets_dir: Path) -> str:
    template = (assets_dir / "template.html").read_text(encoding="utf-8")
    style = (assets_dir / "style.css").read_text(encoding="utf-8")
    app_js = (assets_dir / "app.js").read_text(encoding="utf-8")
    return (
        template
        .replace("__WIKI_TITLE__", "Wiki")
        .replace("<!-- __HEAD_EXTRA__ -->", "")
        .replace("__STYLE__", style)
        .replace("__VENDOR_SCRIPTS__", vendor_scripts_block(assets_dir))
        .replace("__WIKI_DATA__", "")   # serve mode: app.js fetches instead
        .replace("__APP_JS__", app_js)
    )


def latest_mtime(wiki_dir: Path):
    latest = 0.0
    count = 0
    for base in (wiki_dir / "wiki.json", wiki_dir / "content"):
        if base.is_file():
            latest = max(latest, base.stat().st_mtime)
            count += 1
        elif base.is_dir():
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if f.endswith(".md"):
                        count += 1
                        latest = max(latest, (Path(root) / f).stat().st_mtime)
    return latest, count


def make_handler(wiki_dir: Path, assets_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # quiet
            pass

        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path):
            if not path.is_file():
                self._send(404, f"Not found: {path.name}")
                return
            ctype = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
            self._send(200, path.read_bytes(), ctype)

        def do_GET(self):
            route = self.path.split("?", 1)[0]

            if route in ("/", "/index.html"):
                self._send(200, render_index(assets_dir))
                return

            if route == "/__mtime":
                mtime, count = latest_mtime(wiki_dir)
                self._send(200, json.dumps({"mtime": mtime, "count": count}),
                           "application/json")
                return

            if route == "/wiki.json":
                self._send_file(wiki_dir / "wiki.json")
                return

            # served from the skill assets
            if route == "/app.js":
                self._send_file(assets_dir / "app.js")
                return
            if route == "/style.css":
                self._send_file(assets_dir / "style.css")
                return
            if route.startswith("/vendor/"):
                target = (assets_dir / route.lstrip("/")).resolve()
                try:
                    target.relative_to(assets_dir.resolve())  # prevent path traversal
                except ValueError:
                    self._send(403, "Forbidden")
                    return
                self._send_file(target)
                return

            # markdown content and any other relative path resolves against wiki-dir
            rel = route.lstrip("/")
            target = (wiki_dir / rel).resolve()
            try:
                target.relative_to(wiki_dir.resolve())  # prevent path traversal
            except ValueError:
                self._send(403, "Forbidden")
                return
            self._send_file(target)

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Live-preview server for a code2wiki wiki.")
    ap.add_argument("--wiki-dir", required=True, help="dir containing wiki.json and content/")
    ap.add_argument("--assets-dir", required=True, help="skill assets dir")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    wiki_dir = Path(args.wiki_dir).expanduser().resolve()
    assets_dir = Path(args.assets_dir).expanduser().resolve()

    handler = make_handler(wiki_dir, assets_dir)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}"
    print(f"code2wiki live preview → {url}")
    print(f"  wiki-dir : {wiki_dir}")
    print("  Pages reload automatically as files change. Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
