from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import command_parts
from .project import main_file_path, pdf_path, project_info, write_project_info


MIKTEX_ENGINE_ALIASES = {
    "pdflatex": "miktex-pdflatex",
    "xelatex": "miktex-xelatex",
    "lualatex": "miktex-lualatex",
}
MIKTEX_PDFTEX_ENGINES = {
    "pdflatex": ("miktex-pdftex", "pdflatex"),
    "xelatex": ("miktex-xetex", "xelatex"),
    "lualatex": ("miktex-luatex", "lualatex"),
}
DIAGNOSTIC_PATTERN = re.compile(
    r"(?:\bwarning\b|\berror\b|\bfatal\b|\bfailed\b|\bfailure\b|"
    r"emergency stop|undefined control sequence|overfull|underfull|"
    r"file is locked|not found|missing)",
    re.IGNORECASE,
)
MISSING_TEX_FILE_PATTERN = re.compile(r"File [`']([^`']+)[`'] not found")
DEFAULT_COMPILER_ARGUMENTS = ["-interaction=nonstopmode", "-file-line-error", "-synctex=1"]


def project_arguments(info: dict) -> list[str]:
    """Read optional extra compiler arguments from project.json safely."""
    arguments = info.get("arguments", [])
    if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
        print("ltex: project.json `arguments` must be a JSON list of strings; ignoring it")
        return []
    return arguments


def missing_miktex_packages(output: str) -> list[str]:
    """Map common missing LaTeX package files to MiKTeX package names."""
    packages: list[str] = []
    for filename in MISSING_TEX_FILE_PATTERN.findall(output):
        suffix = Path(filename).suffix.lower()
        if suffix not in {".sty", ".cls", ".fd", ".def"}:
            continue
        package = Path(filename).stem
        if package and package not in packages:
            packages.append(package)
    return packages


def install_miktex_packages(packages: list[str], environment: dict[str, str]) -> bool:
    miktex = shutil.which("miktex")
    if miktex is None or not packages:
        return False
    print(f"MiKTeX is installing missing package(s): {', '.join(packages)}")
    try:
        result = subprocess.run(
            [miktex, "packages", "install", *packages],
            text=True,
            capture_output=True,
            env=environment,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("ltex: MiKTeX package installation timed out; check the package repository/network and retry")
        return False
    except OSError as exc:
        print(f"ltex: could not start MiKTeX package installer: {exc}")
        return False
    if result.returncode:
        output = (result.stdout + "\n" + result.stderr).strip()
        if output:
            print(output)
        return False
    return True


def resolve_engine(parts: list[str], distribution: str) -> list[str] | None:
    if distribution == "miktex" and parts[0] in MIKTEX_ENGINE_ALIASES:
        pdftex_engine, fmt = MIKTEX_PDFTEX_ENGINES[parts[0]]
        if shutil.which(pdftex_engine) is not None:
            return [pdftex_engine, f"-fmt={fmt}", *parts[1:]]
        alias = MIKTEX_ENGINE_ALIASES[parts[0]]
        if shutil.which(alias) is not None:
            return [alias, *parts[1:]]
    if shutil.which(parts[0]) is not None:
        return parts
    return None


def compiler_environment(root: Path, distribution: str) -> dict[str, str]:
    # Use the distribution's normal user/system package stores.  Overriding
    # MiKTeX's roots per project looks isolated, but it prevents packages that
    # are already installed by MiKTeX from being found and causes independent
    # package-manager locks in every project.
    return os.environ.copy()


def compiler_diagnostics(output: str) -> list[str]:
    """Extract warnings/errors without echoing normal compiler progress."""
    lines = output.splitlines()
    diagnostics: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("!") or DIAGNOSTIC_PATTERN.search(stripped):
            if stripped not in diagnostics:
                diagnostics.append(stripped)
            # LaTeX usually puts the source line immediately after `! ...`.
            if stripped.startswith("!"):
                for context in lines[index + 1:index + 3]:
                    context = context.strip()
                    if context and context not in diagnostics:
                        diagnostics.append(context)
    return diagnostics


def print_compiler_guide(config: dict[str, str], executable: str) -> None:
    distribution = config["distribution"]
    engine = config["engine"]
    system = platform.system()
    verify = "where" if system == "Windows" else "command -v"
    print()
    print(f"ltex: no usable {engine!r} compiler was found for {distribution!r}.")
    print("ltex: install a LaTeX distribution, then reopen your terminal so PATH is refreshed.")
    if distribution == "miktex":
        print("\nMiKTeX (the configured distribution):")
        print("  Install: https://miktex.org/download")
        if shutil.which("miktex") is not None:
            print("  MiKTeX is already present. Install its compiler links:")
            print("    miktex links install")
    elif distribution == "texlive":
        print("\nTeX Live (the configured distribution):")
        print("  Install guide: https://tug.org/texlive/")
    else:
        print("\nTinyTeX (the configured distribution):")
        print("  Install guide: https://yihui.org/tinytex/")
    if system == "Linux":
        print("\nOn Debian/Ubuntu, TeX Live is also available from the system package manager:")
        print("  sudo apt update")
        print("  sudo apt install texlive-latex-base latexmk")
        print("  ltex config distribution texlive")
        print("  ltex config engine pdflatex")
    elif system == "Darwin":
        print("\nOn macOS, install MacTeX (TeX Live) from the TeX Live site above.")
    elif system == "Windows":
        print("\nOn Windows, use the MiKTeX installer or the TeX Live installer from the links above.")
    print("\nVerify that the engine is now discoverable:")
    print(f"  {verify} {executable}")
    print("Then retry:")
    print("  ltex build")


def build(root: Path, config: dict[str, str], quiet: bool = False) -> bool:
    info = project_info(root)
    main = main_file_path(root, info)
    if not main.exists():
        print(f"ltex: main file not found: {main}")
        return False
    configured_main = root / info.get("main_file", "main.tex")
    if main != configured_main or not (root / "project.json").exists() or "arguments" not in info:
        # Older ltex versions selected the first alphabetic .tex file.  Repair
        # that metadata automatically when a real entrypoint is discovered and
        # move legacy .ltex/project.json metadata into the project root.
        info["main_file"] = str(main.relative_to(root))
        info["pdf_file"] = str(Path("build") / main.with_suffix(".pdf").name)
        info.setdefault("arguments", [])
        write_project_info(root, info)
    engine = config["engine"]
    executable = command_parts(engine) or [engine]
    resolved = resolve_engine(executable, config["distribution"])
    if resolved is None:
        distro = config["distribution"]
        aliases = ""
        if distro == "miktex" and executable[0] in MIKTEX_ENGINE_ALIASES:
            aliases = f" or {MIKTEX_ENGINE_ALIASES[executable[0]]!r}"
        print(f"ltex: {executable[0]!r}{aliases} was not found on PATH (distribution: {distro})")
        if distro == "miktex" and shutil.which("miktex") is not None:
            print("ltex: MiKTeX was found, but its compiler links are missing.")
            print("ltex: run `miktex links install`, then ensure the links directory is on PATH.")
        print_compiler_guide(config, executable[0])
        return False
    executable = resolved
    output_dir = root / "build"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"ltex: could not create build directory {output_dir}: {exc}")
        return False
    try:
        main_argument = str(main.relative_to(root))
    except ValueError:
        main_argument = main.name
    arguments = DEFAULT_COMPILER_ARGUMENTS + project_arguments(info)
    if engine == "latexmk":
        # Keep retrying after a previous failed latexmk run; otherwise
        # latexmk can report "nothing to do" and hide a newly fixed package.
        force_full = False
        try:
            state_data = json.loads((root / ".ltex" / "state.json").read_text(encoding="utf-8"))
            force_full = state_data.get("success") is False
        except (OSError, json.JSONDecodeError):
            pass
        latexmk_options = ["-pdf"]
        if force_full:
            latexmk_options.append("-gg")
        command = executable + latexmk_options + [*arguments, "-halt-on-error"]
        if config["distribution"] == "miktex":
            command.append("-latexoption=-enable-installer")
        command += [f"-outdir={output_dir}", main_argument]
    else:
        compiler_options = ["-enable-installer"] if config["distribution"] == "miktex" else []
        command = executable + compiler_options + [*arguments, "-halt-on-error", f"-output-directory={output_dir}", main_argument]
    if not quiet:
        print(f"Building {main.name} with {executable[0]} ({config['distribution']})...")
    try:
        environment = compiler_environment(root, config["distribution"])
        attempted_packages: set[str] = set()

        def run_compiler():
            result = subprocess.run(command, cwd=root, env=environment, text=True, capture_output=True, check=False)
            combined_output = result.stdout + "\n" + result.stderr
            if result.returncode and "package-manager.lock" in combined_output:
                print("MiKTeX package manager is busy; retrying once...")
                time.sleep(1)
                result = subprocess.run(command, cwd=root, env=environment, text=True, capture_output=True, check=False)
            return result

        result = run_compiler()
        for _ in range(3):
            combined_output = result.stdout + "\n" + result.stderr
            if result.returncode == 0 or config["distribution"] != "miktex":
                break
            packages = [package for package in missing_miktex_packages(combined_output) if package not in attempted_packages]
            if not packages:
                break
            attempted_packages.update(packages)
            if not install_miktex_packages(packages, environment):
                break
            result = run_compiler()
    except OSError as exc:
        print(f"ltex: could not start compiler: {exc}")
        return False
    log = root / ".ltex" / "build.log"
    try:
        log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    except OSError as exc:
        print(f"ltex: warning: could not write {log}: {exc}")
    state = root / ".ltex" / "state.json"
    try:
        state.write_text(json.dumps({
            "success": result.returncode == 0,
            "time": datetime.now(timezone.utc).isoformat(),
            "returncode": result.returncode,
        }, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"ltex: warning: could not write {state}: {exc}")
    diagnostics = compiler_diagnostics(result.stdout + "\n" + result.stderr)
    if diagnostics:
        print("\n--- compiler diagnostics ---")
        print("\n".join(diagnostics))
    if result.returncode:
        print(f"Build failed (exit {result.returncode}). See {log}")
        if "package-manager.lock" in (result.stdout + "\n" + result.stderr):
            print("ltex: MiKTeX's package manager is still locked.")
            print("ltex: stop other MiKTeX/ltex builds, then retry `ltex build`.")
            print(f"ltex: if no build is running, inspect the stale lock under {root / '.ltex' / 'miktex'} before removing it.")
        return False
    if not quiet:
        print(f"Build succeeded: {pdf_path(root, info)}")
    return True
