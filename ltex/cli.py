from __future__ import annotations

import argparse
import os
from queue import Empty, Queue
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import __version__
from .build import build
from .config import DEFAULTS, config_path, command_parts, load_config, save_config, validate_config
from .project import (
    find_main_file,
    find_root,
    main_file_path,
    pdf_path,
    project_info,
    write_metadata_placeholder,
    write_project_gitignore,
    write_project_info,
    write_vscode_tasks,
)
from .template import copy_template
from .update import update

WATCH_EXTENSIONS = {".tex", ".bib", ".sty", ".cls", ".png", ".jpg", ".jpeg", ".pdf"}

FULL_HELP = """ltex - Git-like workflow for LaTeX projects

USAGE
  ltex init [PATH] [--template NAME] [--vscode]   Create a project and build it
  ltex build                           Build once
  ltex work                            Open editor + PDF viewer and watch
  ltex watch [--no-viewer]             Watch, rebuild, and open the PDF viewer
  ltex open                            Open the main .tex file in the editor
  ltex edit                            Alias for `ltex open`
  ltex update                          Update ltex from its GitHub repository
  ltex inverse-search FILE LINE [COL]  Open a source location from a Linux PDF viewer
  ltex forward-search FILE LINE [COL]  Jump from a source location to Zathura
  ltex config                          Read or change global configuration

COMMON WORKFLOW
  ltex init thesis
  cd thesis
  ltex work

PROJECTS
  Projects are marked by a .ltex/ directory. project.json in the project root
  stores the main file, PDF path, and optional compiler arguments. Build state
  and logs are hidden in .ltex/. Generated PDFs and LaTeX auxiliary files are
  kept in build/. The main .tex file is chosen during init;
  templates may keep their main .tex file in a subdirectory; ltex detects the
  entrypoint by preferring main.tex and files containing a document environment.

WORK MODE
  `ltex work` opens the whole project folder in the configured editor and opens
  the current PDF in the configured viewer. It does not open the OS file
  manager. It builds only when the PDF is missing or older than project inputs,
  then rebuilds once per actual source change. Compiler errors are printed in
  the terminal and also saved to .ltex/build.log.

  `ltex watch` opens the PDF viewer by default. Use `ltex watch --no-viewer`
  when only the terminal watcher is wanted. The same flag is accepted by
  `ltex work`.

CONFIGURATION
  ltex config                         Show all settings
  ltex config editor code             Set the editor command
  ltex config viewer zathura          Set the PDF viewer command
  ltex config inverse_search COMMAND  Set the PDF-to-editor callback command
  ltex config distribution miktex    Set miktex, texlive, or tinytex
  ltex config engine latexmk          Set latexmk, pdflatex, xelatex, or lualatex
  ltex config templates_dir PATH      Set the template directory

  Global config: ${XDG_CONFIG_HOME:-~/.config}/ltex/config.toml
  Run the installer again to select editor and viewer defaults interactively.

BUILDING
  New projects default to latexmk, like Overleaf: it reruns LaTeX as needed
  for references, bibliographies, indexes, and cross-file changes. MiKTeX
  uses its normal package store and enables missing-package installation.
  Add extra flags in project.json under "arguments".

MORE HELP
  ltex help init
  ltex help build
  ltex help work
  ltex --help
"""


def _config() -> dict[str, str]:
    try:
        return load_config()
    except ValueError as exc:
        print(f"ltex: {exc}", file=sys.stderr)
        raise SystemExit(2)


TERMINAL_EDITORS = {"vi", "vim", "nvim", "neovim"}


def is_terminal_editor(parts: list[str]) -> bool:
    executable = Path(parts[0]).name.lower()
    if executable.endswith(".exe"):
        executable = executable[:-4]
    return executable in TERMINAL_EDITORS


def windows_command_parts(parts: list[str]) -> list[str]:
    """Resolve Windows command wrappers such as VS Code's ``code.cmd``."""
    if os.name != "nt" or not parts:
        return parts
    resolved = shutil.which(parts[0])
    if resolved and Path(resolved).suffix.lower() in {".bat", ".cmd"}:
        return [resolved, *parts[1:]]
    return parts


def open_path(path: Path, command: str, label: str) -> bool:
    parts = command_parts(command)
    if not parts:
        if label == "editor":
            parts = [os.environ.get("EDITOR", "")]
        else:
            parts = []
    if not parts or not parts[0]:
        print(f"ltex: no {label} configured; use `ltex config {label} ...`")
        return False
    launch_parts = parts + [str(path)]
    launch_cwd = None
    if label == "editor" and path.is_dir() and is_terminal_editor(parts):
        # vim/nvim treat a directory argument differently across versions and
        # configurations. Starting in the directory with no path argument is
        # portable and still exposes the whole multi-file project.
        launch_parts = parts
        launch_cwd = str(path)
    launch_parts = windows_command_parts(launch_parts)
    try:
        subprocess.Popen(launch_parts, cwd=launch_cwd)
    except OSError as exc:
        print(f"ltex: could not start {label}: {exc}")
        return False
    return True


def viewer_name(command: str) -> str:
    parts = command_parts(command)
    return Path(parts[0]).name.lower() if parts else ""


def inverse_search_warning(command: str) -> None:
    name = viewer_name(command)
    if sys.platform.startswith("linux") and name in {"zathura", "okular"}:
        return
    if not name:
        return
    if not sys.platform.startswith("linux"):
        print("ltex: inverse search is supported only on Linux with zathura or okular")
        return
    print(
        f"ltex: inverse search is unavailable for viewer {name!r}; "
        "use zathura or okular for PDF-to-editor navigation"
    )


def open_viewer(path: Path, config: dict[str, str]) -> bool:
    """Open a PDF and configure inverse search where the viewer supports it."""
    command = config["viewer"]
    parts = command_parts(command)
    if not parts:
        print("ltex: no viewer configured; use `ltex config viewer ...`")
        return False
    name = Path(parts[0]).name.lower()
    if sys.platform.startswith("linux") and name == "zathura":
        # Zathura's documented inverse-search placeholders are input and line.
        # ltex defaults the optional column to 1 for this callback.
        callback = f'{config["inverse_search"]} "%{{input}}" "%{{line}}"'
        parts += ["--synctex-editor-command", callback]
    elif not (sys.platform.startswith("linux") and name == "okular"):
        inverse_search_warning(command)
    try:
        subprocess.Popen(windows_command_parts(parts) + [str(path)])
    except OSError as exc:
        print(f"ltex: could not start viewer: {exc}")
        return False
    return True


def forward_search(path: Path, line: int, column: int, config: dict[str, str]) -> int:
    """Jump from a source location to its position in the Zathura PDF."""
    if not sys.platform.startswith("linux"):
        print("ltex: forward search is supported only on Linux with zathura")
        return 2
    source = path.expanduser().resolve()
    try:
        root = find_root(source.parent)
    except FileNotFoundError as exc:
        print(f"ltex: {exc}")
        return 2
    config_parts = command_parts(config["viewer"])
    if not config_parts or Path(config_parts[0]).name.lower() != "zathura":
        print("ltex: forward search requires `ltex config viewer zathura`")
        return 2
    pdf = pdf_path(root, project_info(root)).resolve()
    if not pdf.exists():
        print(f"ltex: PDF not found: {pdf}; run `ltex build` first")
        return 1
    line = max(1, line)
    synctex_column = max(0, column - 1)
    location = f"{line}:{synctex_column}:{source}"
    try:
        subprocess.Popen(windows_command_parts(config_parts + ["--synctex-forward", location, str(pdf)]))
    except OSError as exc:
        print(f"ltex: could not start zathura: {exc}")
        return 1
    return 0


def open_editor_at(path: Path, line: int, column: int, command: str, debug: bool = False) -> bool:
    """Open a source location, reusing an existing GUI editor when supported."""
    parts = command_parts(command)
    if not parts:
        parts = [os.environ.get("EDITOR", "")]
    if not parts or not parts[0]:
        print("ltex: no editor configured; use `ltex config editor ...`")
        return False
    name = Path(parts[0]).name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    # Some SyncTeX viewers report an unknown column as -1. VS Code rejects
    # negative character positions, so normalize it before building --goto.
    line = max(1, line)
    column = max(1, column)
    location = f"{path}:{line}:{column}"
    if name in {"code", "codium"}:
        launch_parts = parts + ["--reuse-window", "--goto", location]
    elif name in {"subl", "sublime_text"}:
        launch_parts = parts + ["--reuse-window", location]
    elif name in {"vim", "nvim", "neovim"}:
        launch_parts = parts + [f"+call cursor({line}, {column})", str(path)]
    else:
        launch_parts = parts + [str(path)]
        print(f"ltex: opening {path}:{line}:{column}; editor focus/reuse is not configured for {name!r}")
    launch_parts = windows_command_parts(launch_parts)
    if debug:
        debug_lines = [
            f"cwd={Path.cwd()}",
            f"source={path} exists={path.exists()}",
            f"line={line} column={column}",
            f"configured_editor={command!r}",
            f"parsed_editor={parts!r}",
            f"resolved_editor={shutil.which(parts[0])!r}",
            f"launch={launch_parts!r}",
        ]
        print("ltex debug: " + " | ".join(debug_lines))
        debug_log = Path(tempfile.gettempdir()) / "ltex-inverse-search-debug.log"
        try:
            with debug_log.open("a", encoding="utf-8") as stream:
                stream.write("ltex debug: " + " | ".join(debug_lines) + "\n")
            print(f"ltex debug log: {debug_log}")
        except OSError as exc:
            print(f"ltex debug: could not write {debug_log}: {exc}")
    try:
        subprocess.Popen(launch_parts)
    except OSError as exc:
        print(f"ltex: could not start editor: {exc}")
        return False
    return True


def project_needs_build(root: Path, info: dict) -> bool:
    pdf = pdf_path(root, info)
    if not pdf.exists():
        return True
    try:
        pdf_time = pdf.stat().st_mtime_ns
    except OSError:
        return True
    for path in root.rglob("*"):
        if not path.is_file() or ".ltex" in path.parts or "build" in path.parts or path.resolve() == pdf.resolve():
            continue
        if path.suffix.lower() in WATCH_EXTENSIONS:
            try:
                if path.stat().st_mtime_ns > pdf_time:
                    return True
            except OSError:
                return True
    return False


def watch(root: Path, config: dict[str, str], launch: bool = False, viewer: bool = True) -> int:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("ltex: watchdog is required for watch; install it with `pip install watchdog`")
        return 2
    info = project_info(root)
    output_pdf = pdf_path(root, info).resolve()
    if project_needs_build(root, info):
        build(root, config, quiet=launch)
    else:
        print("Project is up to date; waiting for changes.")
    if launch:
        # Work on the whole project so multi-file projects can be navigated in
        # the editor.
        open_path(root, config["editor"], "editor")
    if viewer:
        # Both `watch` and `work` open the current PDF unless suppressed.
        open_viewer(output_pdf, config)
    changes: Queue[Path] = Queue()
    signatures: dict[Path, tuple[int, int]] = {}

    def enqueue(path_value: str) -> None:
        path = Path(path_value)
        try:
            resolved = path.resolve()
            stat = path.stat()
        except OSError:
            return
        if ".ltex" in resolved.parts or "build" in resolved.parts or resolved == output_pdf or path.suffix.lower() not in WATCH_EXTENSIONS:
            return
        signature = (stat.st_mtime_ns, stat.st_size)
        if signatures.get(resolved) == signature:
            return
        signatures[resolved] = signature
        changes.put(resolved)

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            enqueue(getattr(event, "dest_path", event.src_path) if event.event_type == "moved" else event.src_path)
    observer = Observer()
    observer.schedule(Handler(), str(root), recursive=True)
    observer.start()
    print("Watching for changes. Press Ctrl-C to stop.")
    try:
        while True:
            try:
                changes.get(timeout=1)
            except Empty:
                continue
            # Editors often emit several events while saving; coalesce them into
            # one build after the write burst has settled.
            time.sleep(0.3)
            while True:
                try:
                    changes.get_nowait()
                except Empty:
                    break
            build(root, config, quiet=launch)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ltex",
        description="Git-like workflow for LaTeX projects",
        epilog="Run `ltex help` for the complete workflow guide.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--debug", action="store_true", help="print inverse-search launch details")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="initialize a project and build it", description="Create a LaTeX project, optionally from a template, and build it immediately.")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--template")
    init.add_argument("--vscode", action="store_true", help="add VS Code watch tasks to the project")
    sub.add_parser("build", help="compile the project once", description="Compile the project once and write .ltex/build.log.")
    watch_parser = sub.add_parser("watch", help="watch, rebuild, and open the PDF viewer", description="Watch LaTeX sources and assets, rebuilding after changes and opening the configured PDF viewer.")
    watch_parser.add_argument("--no-viewer", action="store_true", help="do not open the configured PDF viewer")
    sub.add_parser("open", help="open the main .tex file in the editor", description="Open the project main .tex file in the configured editor.")
    sub.add_parser("edit", help="alias for open", description="Alias for `ltex open`.")
    work_parser = sub.add_parser("work", help="open editor and PDF viewer, then watch", description="Open the whole project in the editor, open the PDF viewer, and watch for changes.")
    work_parser.add_argument("--no-viewer", action="store_true", help="do not open the configured PDF viewer")
    sub.add_parser("update", help="update ltex from GitHub", description="Update the installed ltex tool from its GitHub repository.")
    inverse = sub.add_parser("inverse-search", help="open a source line from a PDF viewer", description="Open a source file and line supplied by a SyncTeX-capable PDF viewer.")
    inverse.add_argument("file")
    inverse.add_argument("line", type=int)
    inverse.add_argument("column", nargs="?", type=int, default=1)
    inverse.add_argument("--debug", action="store_true", default=argparse.SUPPRESS, help="print launch details")
    forward = sub.add_parser("forward-search", help="jump from source to Zathura", description="Jump from a source file and line to the corresponding position in Zathura.")
    forward.add_argument("file")
    forward.add_argument("line", type=int)
    forward.add_argument("column", nargs="?", type=int, default=1)
    cfg = sub.add_parser("config", help="get or set global configuration", description="Read or update global ltex configuration.")
    cfg.add_argument("key", nargs="?")
    cfg.add_argument("value", nargs="?")
    help_parser = sub.add_parser("help", help="show complete help", description="Show complete help or detailed help for one command.")
    help_parser.add_argument("topic", nargs="?", choices=["init", "build", "watch", "open", "edit", "work", "update", "inverse-search", "forward-search", "config"])
    args = parser.parse_args(argv)
    if args.command == "help":
        if args.topic:
            sub.choices[args.topic].print_help()
        else:
            print(FULL_HELP)
        return 0
    if args.command == "update":
        return update()
    config = _config()
    if args.command == "inverse-search":
        if not sys.platform.startswith("linux"):
            print("ltex: inverse search is supported only on Linux with zathura or okular")
            return 2
        return 0 if open_editor_at(Path(args.file).expanduser(), args.line, args.column, config["editor"], args.debug) else 1
    if args.command == "forward-search":
        return forward_search(Path(args.file), args.line, args.column, config)
    if args.command == "config":
        if args.key and args.key not in DEFAULTS:
            print(f"ltex: unknown config key {args.key!r}", file=sys.stderr)
            return 2
        if not args.key:
            for key, value in config.items(): print(f"{key} = {value}")
            return 0
        if args.value is None:
            print(config[args.key]); return 0
        config[args.key] = args.value
        try: validate_config(config)
        except ValueError as exc: print(f"ltex: {exc}", file=sys.stderr); return 2
        print(f"Updated {config_path()}")
        save_config(config); return 0
    if args.command == "init":
        root = Path(args.path).expanduser().resolve(); root.mkdir(parents=True, exist_ok=True)
        if (root / ".ltex").exists(): print(f"ltex: already initialized: {root}", file=sys.stderr); return 2
        try:
            copy_template(root, config["templates_dir"], args.template)
            (root / ".ltex").mkdir()
            write_metadata_placeholder(root)
            write_project_gitignore(root)
            main_file = find_main_file(root).relative_to(root)
            write_project_info(root, {
                "main_file": str(main_file),
                "pdf_file": str(Path("build") / main_file.with_suffix(".pdf").name),
                "template": args.template,
                "arguments": [],
            })
            if args.vscode:
                write_vscode_tasks(root)
        except (OSError, FileNotFoundError) as exc:
            print(f"ltex: init failed: {exc}", file=sys.stderr); return 2
        print(f"Initialized empty ltex project in {root}")
        return 0 if build(root, config) else 1
    try: root = find_root()
    except FileNotFoundError as exc: print(f"ltex: {exc}", file=sys.stderr); return 2
    if args.command == "build": return 0 if build(root, config) else 1
    if args.command in {"open", "edit"}:
        return 0 if open_path(main_file_path(root, project_info(root)), config["editor"], "editor") else 1
    if args.command == "watch": return watch(root, config, viewer=not args.no_viewer)
    return watch(root, config, launch=True, viewer=not args.no_viewer)


if __name__ == "__main__":
    raise SystemExit(main())
