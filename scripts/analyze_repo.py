#!/usr/bin/env python3
"""Analyze a code repository and emit a structured snapshot as JSON.

Standard library only. Produces analysis.json with: a pruned directory tree,
language/LOC breakdown, detected build tools and dependencies, candidate entry
points, config files, and git signal (most-changed files, recent commits,
contributors). This gives the wiki planner a cheap, deterministic starting
point so subagents don't have to rediscover the basics.

Usage:
  python3 analyze_repo.py <repo-path> [--out analysis.json] [--max-tree-entries 400]
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Directories we never want to descend into.
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor",
    "dist", "build", "out", "target", ".next", ".nuxt", ".svelte-kit",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", ".tox", ".gradle", ".idea", ".vscode",
    "coverage", ".cache", ".turbo", ".parcel-cache", "site-packages",
    ".code2wiki", ".terraform", "Pods",
}

# Extension -> language label, for the LOC/size breakdown.
EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript (JSX)",
    ".ts": "TypeScript", ".tsx": "TypeScript (TSX)", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP", ".c": "C", ".h": "C/C++ header",
    ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++ header",
    ".cs": "C#", ".swift": "Swift", ".m": "Objective-C", ".scala": "Scala",
    ".sh": "Shell", ".bash": "Shell", ".sql": "SQL", ".r": "R",
    ".dart": "Dart", ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang",
    ".clj": "Clojure", ".vue": "Vue", ".svelte": "Svelte",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".less": "LESS",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".md": "Markdown", ".proto": "Protobuf", ".graphql": "GraphQL", ".gql": "GraphQL",
}

# Build/manifest files -> (ecosystem label). Their presence reveals the stack.
MANIFESTS = {
    "package.json": "Node.js / npm",
    "yarn.lock": "Node.js / yarn",
    "pnpm-lock.yaml": "Node.js / pnpm",
    "requirements.txt": "Python / pip",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "Pipfile": "Python / pipenv",
    "go.mod": "Go modules",
    "Cargo.toml": "Rust / Cargo",
    "pom.xml": "Java / Maven",
    "build.gradle": "Java / Gradle",
    "build.gradle.kts": "Kotlin / Gradle",
    "Gemfile": "Ruby / Bundler",
    "composer.json": "PHP / Composer",
    "mix.exs": "Elixir / Mix",
    "pubspec.yaml": "Dart / Flutter",
    "Makefile": "Make",
    "Taskfile.yml": "Task",
    "CMakeLists.txt": "CMake",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
}

# Files worth flagging as configuration the wiki should mention.
CONFIG_HINTS = (
    "tsconfig", "babel.config", ".eslintrc", ".prettierrc", "webpack",
    "vite.config", "rollup.config", "next.config", "nuxt.config",
    "tailwind.config", "jest.config", "vitest.config", "playwright.config",
    ".env.example", "config.yaml", "config.yml", "settings.py", "application.yml",
    "application.properties", "serverless.yml", "terraform",
)

ENTRY_HINTS = (
    "main.py", "__main__.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "index.js", "index.ts", "main.js", "main.ts", "server.js", "server.ts",
    "app.js", "app.ts", "main.go", "main.rs", "Main.java", "index.html",
    "cli.py", "cli.js", "cli.ts",
)

TEXT_READ_LIMIT = 2_000_000  # don't try to count lines on files bigger than this


def is_probably_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(2048)
        return b"\x00" in chunk
    except OSError:
        return True


def count_lines(path: Path) -> int:
    try:
        if path.stat().st_size > TEXT_READ_LIMIT:
            return 0
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def walk_repo(repo: Path):
    """Yield (path, rel_path) for files, skipping noise directories."""
    for root, dirs, files in os.walk(repo):
        # prune in-place so os.walk doesn't descend
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".git")]
        for name in files:
            p = Path(root) / name
            yield p, p.relative_to(repo)


def build_tree(repo: Path, max_entries: int) -> dict:
    """A pruned, depth-limited directory tree for orientation."""
    root = {"name": repo.name, "type": "dir", "children": []}
    nodes = {Path("."): root}
    count = 0
    truncated = False

    entries = []
    for root_dir, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".git"))
        rel_dir = Path(root_dir).relative_to(repo)
        depth = 0 if rel_dir == Path(".") else len(rel_dir.parts)
        if depth > 4:  # cap depth to keep the tree readable
            dirs[:] = []
            continue
        for d in dirs:
            entries.append((rel_dir / d, "dir"))
        for f in sorted(files):
            entries.append((rel_dir / f, "file"))

    for rel, kind in entries:
        if count >= max_entries:
            truncated = True
            break
        parent = nodes.get(rel.parent)
        if parent is None:
            continue
        node = {"name": rel.name, "type": kind}
        if kind == "dir":
            node["children"] = []
            nodes[rel] = node
        parent.setdefault("children", []).append(node)
        count += 1

    return {"tree": root, "truncated": truncated, "shown_entries": count}


def read_text(path: Path, limit: int = 60_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def parse_dependencies(repo: Path, manifests_found: dict) -> dict:
    """Light-touch dependency extraction for the most common ecosystems."""
    deps = {}

    pkg = repo / "package.json"
    if pkg.exists():
        try:
            data = json.loads(read_text(pkg))
            deps["npm"] = {
                "dependencies": sorted((data.get("dependencies") or {}).keys()),
                "devDependencies": sorted((data.get("devDependencies") or {}).keys()),
                "scripts": data.get("scripts") or {},
            }
        except (ValueError, OSError):
            pass

    req = repo / "requirements.txt"
    if req.exists():
        lines = [l.strip() for l in read_text(req).splitlines()]
        deps["pip"] = [l for l in lines if l and not l.startswith("#")]

    pyproject = repo / "pyproject.toml"
    if pyproject.exists():
        # crude scan; avoids a TOML dependency
        text = read_text(pyproject)
        deps["pyproject_present"] = True
        if "[tool.poetry" in text:
            deps["python_tool"] = "poetry"
        elif "[project]" in text:
            deps["python_tool"] = "pep621"

    gomod = repo / "go.mod"
    if gomod.exists():
        reqs = []
        for line in read_text(gomod).splitlines():
            line = line.strip()
            if line.startswith("require ") or (line and "/" in line and not line.startswith(("module", "go ", ")", "(", "//"))):
                reqs.append(line.replace("require ", "").strip())
        deps["go"] = reqs[:200]

    cargo = repo / "Cargo.toml"
    if cargo.exists():
        deps["cargo_present"] = True

    return deps


def git_signal(repo: Path) -> dict:
    """Best-effort git metadata; returns {} if not a git repo or git is absent."""
    def run(args):
        try:
            out = subprocess.run(
                ["git", "-C", str(repo)] + args,
                capture_output=True, text=True, timeout=20,
            )
            return out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    head = run(["rev-parse", "--short", "HEAD"])
    if not head:
        return {}

    info = {"head_commit": head}
    info["branch"] = run(["rev-parse", "--abbrev-ref", "HEAD"])

    log = run(["log", "-15", "--pretty=format:%h\t%an\t%ad\t%s", "--date=short"])
    info["recent_commits"] = [
        dict(zip(("hash", "author", "date", "subject"), line.split("\t", 3)))
        for line in log.splitlines() if "\t" in line
    ]

    contributors = run(["shortlog", "-sne", "HEAD"])
    info["contributors"] = [c.strip() for c in contributors.splitlines()[:15] if c.strip()]

    # most-changed files over recent history = likely architectural hotspots
    names = run(["log", "--name-only", "--pretty=format:", "-300"])
    if names:
        freq = Counter(n for n in names.splitlines() if n.strip())
        info["hotspot_files"] = [
            {"file": f, "changes": c} for f, c in freq.most_common(20)
        ]
    return info


def find_docs(repo: Path) -> list:
    docs = []
    for name in ("README", "README.md", "README.rst", "README.txt",
                 "CONTRIBUTING.md", "ARCHITECTURE.md", "CHANGELOG.md", "docs"):
        p = repo / name
        if p.exists():
            docs.append(name)
    return docs


def analyze(repo: Path, max_tree_entries: int) -> dict:
    lang_files = Counter()
    lang_loc = Counter()
    manifests_found = {}
    config_files = []
    entry_points = []
    total_files = 0
    total_loc = 0

    for path, rel in walk_repo(repo):
        total_files += 1
        name = path.name
        ext = path.suffix.lower()

        if name in MANIFESTS:
            manifests_found[str(rel)] = MANIFESTS[name]
        if any(h in name for h in CONFIG_HINTS):
            config_files.append(str(rel))
        if name in ENTRY_HINTS:
            entry_points.append(str(rel))

        if ext in EXT_LANG and not is_probably_binary(path):
            loc = count_lines(path)
            lang_files[EXT_LANG[ext]] += 1
            lang_loc[EXT_LANG[ext]] += loc
            total_loc += loc

    languages = sorted(
        ({"language": k, "files": lang_files[k], "loc": lang_loc[k]} for k in lang_files),
        key=lambda d: d["loc"], reverse=True,
    )

    return {
        "repo_path": str(repo),
        "repo_name": repo.name,
        "totals": {"files_scanned": total_files, "code_loc": total_loc},
        "languages": languages,
        "primary_language": languages[0]["language"] if languages else None,
        "build_tools": manifests_found,
        "dependencies": parse_dependencies(repo, manifests_found),
        "entry_points": sorted(set(entry_points)),
        "config_files": sorted(set(config_files))[:60],
        "docs": find_docs(repo),
        "git": git_signal(repo),
        "directory_tree": build_tree(repo, max_tree_entries),
    }


def main():
    ap = argparse.ArgumentParser(description="Analyze a repo and emit analysis.json")
    ap.add_argument("repo", help="path to the repository")
    ap.add_argument("--out", default=None, help="output JSON path (default: stdout)")
    ap.add_argument("--max-tree-entries", type=int, default=400)
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        sys.exit(1)

    result = analyze(repo, args.max_tree_entries)
    text = json.dumps(result, indent=2)

    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        langs = ", ".join(f"{l['language']} ({l['loc']} LOC)" for l in result["languages"][:5])
        print(f"Wrote {out}")
        print(f"  {result['totals']['files_scanned']} files scanned, "
              f"{result['totals']['code_loc']} LOC")
        print(f"  Languages: {langs or 'none detected'}")
        print(f"  Build tools: {', '.join(result['build_tools'].values()) or 'none detected'}")
    else:
        print(text)


if __name__ == "__main__":
    main()
