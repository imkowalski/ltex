"""Connect PDF inverse search to an existing Neovim RPC server."""

from __future__ import annotations

import os
from pathlib import Path

from .project import find_root


def vim_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def server_file(path: Path) -> Path | None:
    try:
        root = find_root(path if path.is_dir() else path.parent)
    except FileNotFoundError:
        return None
    return root / ".ltex" / "nvim-server"


def startup_arguments(path: Path) -> list[str]:
    """Remember Neovim's own socket when ltex opens a project editor."""
    registration = server_file(path)
    if registration is None:
        return []
    return ["--cmd", f"call writefile([v:servername], {vim_string(str(registration))})"]


def remote_command(
    path: Path, line: int, column: int, parts: list[str], server: str = ""
) -> list[str] | None:
    """Choose an explicit, inherited, or project-registered RPC server."""
    if not server:
        for index, part in enumerate(parts[:-1]):
            if part in {"--server", "--listen"}:
                server = parts[index + 1]
                break
    server = server or os.environ.get("NVIM", "")
    if not server:
        registration = server_file(path)
        if registration is not None:
            try:
                server = registration.read_text(encoding="utf-8").strip()
            except OSError:
                pass
    if not server:
        return None
    # An expression avoids treating key-like text in filenames as keystrokes.
    expression = (
        f"execute('drop ' . fnameescape({vim_string(str(path.resolve()))}))"
        f" . cursor({max(1, line)}, {max(1, column)})"
        " . execute('normal! zvzz')"
    )
    return [parts[0], "--server", server, "--remote-expr", expression]
