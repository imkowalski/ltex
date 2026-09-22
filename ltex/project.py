from __future__ import annotations

import json
import re
from pathlib import Path

METADATA = ".ltex"
PROJECT_FILE = "project.json"
GITIGNORE = """# ltex-generated files
.ltex/*
!.ltex/.gitkeep
build/
"""

VSCODE_TASKS = {
    "version": "2.0.0",
    "tasks": [
        {
            "label": "Watch report (No PDF Viewer)",
            "type": "shell",
            "command": "ltex",
            "args": ["watch", "--no-viewer"],
            "options": {"cwd": "${workspaceFolder}"},
            "isBackground": True,
            "problemMatcher": [],
            "presentation": {
                "reveal": "silent",
                "panel": "dedicated",
                "group": "report-watch",
            },
        },
        {
            "label": "Watch report (With PDF Viewer)",
            "type": "shell",
            "command": "ltex",
            "args": ["watch"],
            "options": {"cwd": "${workspaceFolder}"},
            "isBackground": True,
            "problemMatcher": [],
            "presentation": {
                "reveal": "silent",
                "panel": "dedicated",
                "group": "report-watch",
            },
        },
        {
            "label": "Forward search in Zathura",
            "type": "shell",
            "command": "ltex",
            "args": ["forward-search", "${file}", "${lineNumber}", "${columnNumber}"],
            "options": {"cwd": "${workspaceFolder}"},
            "problemMatcher": [],
            "presentation": {"reveal": "never", "panel": "dedicated"},
        },
    ],
}


def find_root(start: Path | None = None) -> Path:
    path = (start or Path.cwd()).resolve()
    for candidate in (path, *path.parents):
        if (candidate / METADATA).is_dir():
            return candidate
    raise FileNotFoundError("not an ltex project (no .ltex directory found)")


def metadata_path(root: Path) -> Path:
    # New projects keep this beside the source files.  Read the old hidden
    # location as a backwards-compatible migration path.
    project_file = root / PROJECT_FILE
    return project_file if project_file.exists() else root / METADATA / PROJECT_FILE


def write_project_gitignore(root: Path) -> None:
    """Create default ignore rules without replacing a user's .gitignore."""
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if GITIGNORE not in existing:
        separator = "\n" if existing and not existing.endswith("\n") else ""
        path.write_text(existing + separator + GITIGNORE, encoding="utf-8")


def write_metadata_placeholder(root: Path) -> None:
    """Keep the .ltex project marker present in Git without tracking state."""
    (root / METADATA / ".gitkeep").write_text("", encoding="utf-8")


def project_info(root: Path) -> dict:
    path = metadata_path(root)
    if not path.exists():
        return {"main_file": "main.tex", "pdf_file": "build/main.pdf", "arguments": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid project metadata: {path}: {exc}") from exc


def _is_document_entrypoint(path: Path) -> bool:
    """Return whether a TeX file looks like a document entrypoint.

    Section files such as ``0-Config.tex`` commonly contain commands that are
    only defined by the real document's preamble.  Looking for a document
    environment lets us avoid selecting those files just because their names
    sort first.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(
        re.search(r"\\begin\s*\{\s*document\s*\}", text)
        or re.search(r"\\documentclass(?:\s*\[[^]]*\])?\s*\{", text)
    )


def find_main_file(root: Path) -> Path:
    """Find the most likely document entrypoint in a project.

    Prefer ``main.tex`` (including nested template directories), then files
    containing a document environment or document class.  The final fallback
    preserves the old behavior for unusual templates while still ignoring
    generated and metadata directories.
    """
    candidates = sorted(
        (
            path
            for path in root.rglob("*.tex")
            if ".ltex" not in path.parts and "build" not in path.parts
        ),
        key=lambda path: (len(path.relative_to(root).parts), str(path).lower()),
    )
    if not candidates:
        return root / "main.tex"

    named = [path for path in candidates if path.name.lower() == "main.tex"]
    if named:
        return named[0]
    entrypoints = [path for path in candidates if _is_document_entrypoint(path)]
    return entrypoints[0] if entrypoints else candidates[0]


def main_file_path(root: Path, info: dict) -> Path:
    """Return the configured main file, correcting old fragment selections."""
    configured = root / info.get("main_file", "main.tex")
    if configured.exists() and _is_document_entrypoint(configured):
        return configured
    detected = find_main_file(root)
    return detected if detected.exists() else configured


def pdf_path(root: Path, info: dict) -> Path:
    """Return the generated PDF path, migrating legacy root-level metadata."""
    main = main_file_path(root, info).relative_to(root)
    configured = Path(info.get("pdf_file", ""))
    if not configured or configured.parts[0] != "build":
        configured = Path("build") / (configured.name or main.with_suffix(".pdf").name)
    return root / configured


def write_project_info(root: Path, info: dict) -> None:
    (root / METADATA).mkdir(exist_ok=True)
    (root / PROJECT_FILE).write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")


def write_vscode_tasks(root: Path) -> None:
    path = root / ".vscode" / "tasks.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(VSCODE_TASKS, indent=2) + "\n", encoding="utf-8")
