from __future__ import annotations

import shutil
import subprocess


GITHUB_SOURCE = "git+https://github.com/imkowalski/ltex.git"


def update() -> int:
    """Upgrade the user-installed ltex tool from the project's GitHub repo."""
    uv = shutil.which("uv")
    if uv is None:
        print("ltex: uv is required to update the installed tool, but it was not found on PATH.")
        print("ltex: install uv from https://docs.astral.sh/uv/getting-started/installation/")
        print("ltex: or rerun the ltex installer from https://github.com/imkowalski/ltex")
        return 2

    command = [
        uv,
        "tool",
        "install",
        "--force",
        "--refresh",
        "--from",
        GITHUB_SOURCE,
        "--with",
        "watchdog",
        "ltex",
    ]
    print("Updating ltex from GitHub...")
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        print(f"ltex: could not start uv: {exc}")
        return 1
    if result.returncode:
        print(f"ltex: update failed (uv exited with status {result.returncode})")
        return result.returncode
    print("ltex updated successfully.")
    return 0
