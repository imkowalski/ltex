from __future__ import annotations

import shutil
from pathlib import Path

BUILTIN = {"main.tex": r"""\documentclass{article}
\usepackage[utf8]{inputenc}
\title{New ltex Project}
\author{}
\date{\today}
\begin{document}
\maketitle

Start writing here.
\end{document}
"""}


def copy_template(root: Path, templates_dir: str, name: str | None) -> None:
    if not name:
        for filename, content in BUILTIN.items():
            target = root / filename
            if not target.exists():
                target.write_text(content, encoding="utf-8")
        return
    base = Path(templates_dir).expanduser() if templates_dir else None
    source = base / name if base else None
    if not source or not source.is_dir():
        raise FileNotFoundError(f"template {name!r} was not found in {base or 'configured templates_dir'}")
    for item in source.iterdir():
        target = root / item.name
        if target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

