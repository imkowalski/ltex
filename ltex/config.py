from __future__ import annotations

import os
import shlex
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and older
    import tomli as tomllib

VALID_DISTRIBUTIONS = {"miktex", "texlive", "tinytex"}
VALID_ENGINES = {"pdflatex", "xelatex", "lualatex", "latexmk"}
DEFAULTS = {
    "editor": "",
    "viewer": "",
    "inverse_search": "ltex inverse-search",
    "distribution": "miktex",
    "engine": "latexmk",
    "templates_dir": "~/.config/ltex/templates",
}
ENGINE_DEFAULTS = {"miktex": "latexmk", "texlive": "latexmk", "tinytex": "latexmk"}


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ltex"


def config_path() -> Path:
    return config_dir() / "config.toml"


def load_config() -> dict[str, str]:
    values = DEFAULTS.copy()
    path = config_path()
    engine_was_set = False
    if path.exists():
        try:
            with path.open("rb") as fh:
                raw = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"cannot read config {path}: {exc}") from exc
        for key in values:
            if key in raw and isinstance(raw[key], str):
                values[key] = raw[key]
                if key == "engine":
                    engine_was_set = True
    if values["distribution"] not in VALID_DISTRIBUTIONS:
        raise ValueError(f"invalid distribution {values['distribution']!r}; choose: {', '.join(sorted(VALID_DISTRIBUTIONS))}")
    if not engine_was_set:
        values["engine"] = ENGINE_DEFAULTS[values["distribution"]]
    if values["engine"] not in VALID_ENGINES:
        raise ValueError(f"invalid engine {values['engine']!r}; choose: {', '.join(sorted(VALID_ENGINES))}")
    return values


def validate_config(values: dict[str, str]) -> None:
    if values["distribution"] not in VALID_DISTRIBUTIONS:
        raise ValueError(f"invalid distribution {values['distribution']!r}; choose: {', '.join(sorted(VALID_DISTRIBUTIONS))}")
    if values["engine"] not in VALID_ENGINES:
        raise ValueError(f"invalid engine {values['engine']!r}; choose: {', '.join(sorted(VALID_ENGINES))}")


def save_config(values: dict[str, str]) -> Path:
    config_dir().mkdir(parents=True, exist_ok=True)
    lines = []
    for key in DEFAULTS:
        value = values.get(key, "")
        lines.append(f"{key} = {value!r}")
    path = config_path()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def command_parts(command: str) -> list[str]:
    if not command.strip():
        return []
    if os.name != "nt":
        return shlex.split(command)

    try:
        import ctypes
        from ctypes import wintypes

        argc = ctypes.c_int()
        shell32 = ctypes.windll.shell32
        shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
        ctypes.windll.kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        ctypes.windll.kernel32.LocalFree.restype = wintypes.HLOCAL
        argv = shell32.CommandLineToArgvW(command, ctypes.byref(argc))
        if not argv:
            raise OSError("CommandLineToArgvW returned NULL")
        try:
            return [argv[index] for index in range(argc.value)]
        finally:
            ctypes.windll.kernel32.LocalFree(argv)
    except (AttributeError, OSError, ValueError):
        # Last-resort fallback for non-standard Windows Python runtimes.
        return shlex.split(command, posix=False)
