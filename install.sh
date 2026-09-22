#!/usr/bin/env sh
set -eu

# Python-agnostic installer: uv supplies and isolates the Python runtime.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Remove stale setuptools output so local source files are packaged afresh.
if [ -d "$ROOT/build" ]; then
    rm -rf -- "$ROOT/build"
fi

if command -v uv >/dev/null 2>&1; then
    UV=uv
else
    if ! command -v curl >/dev/null 2>&1; then
        echo "ltex: uv is not installed and curl is unavailable." >&2
        echo "Install uv from https://docs.astral.sh/uv/getting-started/installation/" >&2
        exit 1
    fi
    echo "uv was not found; installing the standalone uv tool manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    UV="${UV_INSTALL_DIR:-$HOME/.local/bin}/uv"
    if [ ! -x "$UV" ]; then
        UV=$(command -v uv 2>/dev/null || true)
    fi
    if [ -z "$UV" ] || [ ! -x "$UV" ]; then
        echo "ltex: uv was installed, but its executable could not be located." >&2
        exit 1
    fi
fi

"$UV" tool install --force --no-cache --reinstall-package ltex --from "$ROOT" --with watchdog ltex
if ! "$UV" tool update-shell; then
    echo "ltex: could not update the shell PATH automatically." >&2
fi
echo "ltex installed and its user tool directory was added to PATH."
echo "Open a new terminal (or reload your shell config), then run: ltex --help"
echo "Tool directory:"
"$UV" tool dir --bin

first_available() {
    for candidate in "$@"; do
        if command -v "$candidate" >/dev/null 2>&1; then
            printf '%s' "$candidate"
            return
        fi
    done
}

if [ -t 0 ] && [ -t 1 ]; then
    TOOL_BIN=$("$UV" tool dir --bin)
    LTEX_BIN="$TOOL_BIN/ltex"
    CURRENT_EDITOR=$($LTEX_BIN config editor 2>/dev/null || true)
    CURRENT_VIEWER=$($LTEX_BIN config viewer 2>/dev/null || true)
    EDITOR_DEFAULT=${CURRENT_EDITOR:-${EDITOR:-$(first_available nvim code vim nano vi)}}
    VIEWER_DEFAULT=${CURRENT_VIEWER:-${LTEX_VIEWER:-$(first_available zathura evince okular xdg-open open)}}

    printf '\nChoose the default editor command [%s]: ' "$EDITOR_DEFAULT"
    IFS= read -r EDITOR_CHOICE || EDITOR_CHOICE=
    EDITOR_CHOICE=${EDITOR_CHOICE:-$EDITOR_DEFAULT}
    printf 'Choose the default PDF viewer command [%s]: ' "$VIEWER_DEFAULT"
    IFS= read -r VIEWER_CHOICE || VIEWER_CHOICE=
    VIEWER_CHOICE=${VIEWER_CHOICE:-$VIEWER_DEFAULT}

    [ -n "$EDITOR_CHOICE" ] && "$LTEX_BIN" config editor "$EDITOR_CHOICE"
    [ -n "$VIEWER_CHOICE" ] && "$LTEX_BIN" config viewer "$VIEWER_CHOICE"
    echo "Saved editor and viewer defaults."
else
    echo "Non-interactive install: editor/viewer selection skipped."
    echo "Set them later with: ltex config editor COMMAND and ltex config viewer COMMAND"
fi
