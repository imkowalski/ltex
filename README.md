# ltex

`ltex` is a Git-like command-line workflow for LaTeX projects. It initializes a
project, builds it, opens the project in an editor and PDF viewer, and rebuilds
when source files change. New projects use `latexmk` by default, giving an
Overleaf-style multi-pass build for references, bibliographies, indexes, and
other generated dependencies.

## Install ltex

The recommended installers do not require an existing Python or Conda setup.
They use `uv`, which supplies an isolated Python runtime and installs `ltex` as
a user command.

Linux and macOS:

```bash
./install.sh
```

Windows PowerShell:

```powershell
.\install.ps1
```

Windows Command Prompt:

```bat
install.cmd
```

The installer adds the user tool directory to PATH and interactively asks for
the default editor and PDF viewer. Open a new terminal afterward so the PATH
change is loaded. Re-run the installer after updating this checkout.

For an existing Conda environment, the included `environment.yml` is also
available:

```bash
conda env create -f environment.yml
conda activate ltex
ltex config editor code
ltex config viewer zathura
```

## Install a LaTeX distribution

`ltex` is only the project workflow. A LaTeX distribution must be installed
separately because it provides the actual compilers.

### Recommended: MiKTeX

MiKTeX is the default `ltex` distribution and works across Linux, macOS, and
Windows. Install it from [miktex.org/download](https://miktex.org/download).

On Linux, if MiKTeX is already installed but only the `miktex` command is
available, create its compiler links:

```bash
miktex links install
```

Then verify one of these commands works:

```bash
command -v pdflatex
command -v miktex-pdflatex
command -v miktex-pdftex
```

`ltex` recognizes all three MiKTeX layouts. For the lower-level layout it uses
the same command as the working MiKTeX project pattern:

```bash
miktex-pdftex -fmt=pdflatex
```

### TeX Live

TeX Live is a standard choice on Linux and is available from
[tug.org/texlive](https://tug.org/texlive/). On Debian or Ubuntu, the minimal
setup for the built-in template is:

```bash
sudo apt update
sudo apt install texlive-latex-base latexmk
ltex config distribution texlive
ltex config engine pdflatex
```

Install additional TeX Live packages if a project uses packages outside the
base installation. On macOS, the native TeX Live bundle is called
[MacTeX](https://tug.org/mactex/).

### TinyTeX

TinyTeX is a lightweight TeX Live distribution. Follow the installation guide
at [yihui.org/tinytex](https://yihui.org/tinytex/), then select it in `ltex`:

```bash
ltex config distribution tinytex
ltex config engine pdflatex
```

Check the selected compiler before building:

```bash
ltex config
pdflatex --version
```

If no compiler is found, `ltex build` prints an OS-specific installation guide,
PATH checks, and the appropriate configuration commands.

## Basic workflow

Create and build a project:

```bash
ltex init thesis
cd thesis
```

Start a working session:

```bash
ltex work
```

`ltex work`:

- Opens the entire project folder in the configured editor, supporting
  multi-file projects.
- Opens the current PDF in the configured viewer.
- Does not open the OS file manager.
- Builds at startup only if the PDF is missing or older than project inputs.
- Writes the PDF, `.aux`, `.log`, and other generated LaTeX files under
  `build/`; the full ltex log remains hidden at `.ltex/build.log`.
- Watches `.tex`, `.bib`, `.sty`, `.cls`, and common image files.
- Rebuilds once per actual change and prints only warnings/errors in the
  terminal.

`ltex watch` opens the configured PDF viewer by default while watching. Use
`ltex watch --no-viewer` to keep the watcher in the terminal without launching
the viewer. `ltex work --no-viewer` supports the same override. For Vim or
Neovim, `ltex work` starts the editor in the project directory without passing
the directory as a file argument; `ltex open` continues to open the selected
main `.tex` file directly.

Other commands:

```text
ltex build                 Build once
ltex watch                 Watch, rebuild, and open the PDF viewer
ltex watch --no-viewer     Watch and rebuild without opening the viewer
ltex open                  Open the main .tex file in the editor
ltex edit                  Alias for ltex open
ltex config                Show or change global configuration
ltex help                  Show complete help
ltex help work             Show command-specific help
```

## Templates

Global configuration is stored in:

```text
${XDG_CONFIG_HOME:-~/.config}/ltex/config.toml
```

Set a templates directory and initialize from a template:

```bash
ltex config templates_dir ~/.config/ltex/templates
ltex init report --template report
```

Each template is a subdirectory containing its `.tex`, `.bib`, `.sty`, `.cls`,
asset, and other project files. If no template is selected, `ltex` creates a
small built-in article project. For a template, ltex selects `main.tex` even
when it is nested in a subdirectory; otherwise it selects the first `.tex`
file that contains a document environment or document class. This means
included section files such as `0-Config.tex` are not accidentally compiled as
the project entry point.

## Configuration

```bash
ltex config                         # show all settings
ltex config editor code             # editor command
ltex config viewer zathura          # PDF viewer command
ltex config distribution miktex     # miktex, texlive, or tinytex
ltex config engine latexmk          # latexmk is the default; pdflatex, xelatex, lualatex also work
ltex config templates_dir PATH      # template directory
```

Commands may include arguments, for example `code --reuse-window` or a viewer
option. The installer saves editor and viewer choices automatically.

## Project files and diagnostics

Each project has a `project.json` in its root containing:

- `main_file` — the document entrypoint
- `pdf_file` — the generated PDF path, normally under `build/`
- `arguments` — optional extra compiler arguments, for example
  `["-shell-escape"]`

Each project also has a `.ltex/` directory containing:

- `build.log` — complete compiler output
- `state.json` — last build result and timestamp
- `miktex/` — legacy project-local MiKTeX state, if created by an older ltex version

  Generated PDF and LaTeX auxiliary files are kept in the project `build/`
  directory rather than beside the source files.

Compiler warnings and errors are printed in the terminal during `work` and are
also retained in `.ltex/build.log`.

Projects created by older ltex versions may still have `.ltex/project.json`.
That location remains readable; the next metadata update writes the file to the
project root.
