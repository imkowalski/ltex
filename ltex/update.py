from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


GITHUB_SOURCE = "git+https://github.com/imkowalski/ltex.git"


def _schedule_windows_update(command: list[str]) -> int:
    """Run uv after this process exits so Windows can unlock the tool files."""
    script_handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix="-ltex-update.cmd",
        delete=False,
    )
    script_path = Path(script_handle.name)
    log_path = script_path.with_suffix(".log")
    try:
        command_line = subprocess.list2cmdline(command)
        script_handle.write(
            "@echo off\r\n"
            "timeout /t 3 /nobreak >nul\r\n"
            f"{command_line} > \"{log_path}\" 2>&1\r\n"
            f"del \"{script_path}\" >nul 2>&1\r\n"
        )
        script_handle.close()
        detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        subprocess.Popen(
            ["cmd.exe", "/d", "/c", "start", "", "/b", "cmd.exe", "/d", "/c", "call", str(script_path)],
            creationflags=detached | new_group,
            close_fds=True,
        )
    except OSError as exc:
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"ltex: could not schedule the Windows update: {exc}")
        return 1
    finally:
        if not script_handle.closed:
            script_handle.close()
    print("ltex update scheduled; it will finish after this command exits.")
    print(f"ltex: update output will be saved to {log_path}")
    return 0


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
    if os.name == "nt":
        return _schedule_windows_update(command)
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
