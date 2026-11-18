import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ltex.build import build, compiler_diagnostics
from ltex.project import write_project_info


class CompilerDiagnosticsTests(unittest.TestCase):
    def test_file_line_errors_keep_the_offending_command_and_come_before_warnings(self):
        output = (
            "This is normal compiler progress\n"
            "LaTeX Warning: Reference `missing' undefined.\n"
            "notes/chapter with spaces.tex:17: Undefined control sequence.\n"
            "l.17 Some text \\unknownmacro\n"
            "                           .\n"
        )
        diagnostics = compiler_diagnostics(output)
        self.assertEqual(diagnostics[:3], [
            "notes/chapter with spaces.tex:17: Undefined control sequence.",
            r"l.17 Some text \unknownmacro",
            ".",
        ])
        self.assertEqual(diagnostics[-1], "LaTeX Warning: Reference `missing' undefined.")
        self.assertNotIn("This is normal compiler progress", diagnostics)

    def test_file_line_errors_without_the_word_error_are_included(self):
        diagnostics = compiler_diagnostics(
            "chapter.tex:8: Missing $ inserted.\n"
            "<inserted text>\n"
            "                $\n"
        )
        self.assertEqual(diagnostics, ["chapter.tex:8: Missing $ inserted.", "<inserted text>", "$"])

    def test_windows_file_locations_preserve_source_context(self):
        diagnostics = compiler_diagnostics(
            "C:\\My Documents\\chapter.tex:12: Undefined control sequence.\n"
            "l.12 \\notdefined\n"
            "\n"
        )
        self.assertEqual(diagnostics, [
            r"C:\My Documents\chapter.tex:12: Undefined control sequence.",
            r"l.12 \notdefined",
        ])

    def test_classic_tex_errors_still_include_expansion_context(self):
        diagnostics = compiler_diagnostics(
            "! Undefined control sequence.\n"
            "\\wrapper ->\\notdefined\n"
            "l.3 \\wrapper\n"
        )
        self.assertEqual(diagnostics, [
            "! Undefined control sequence.", r"\wrapper ->\notdefined", r"l.3 \wrapper",
        ])

    def test_failed_build_reports_the_source_cause_without_retrying_or_rewriting_sources(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".ltex").mkdir()
            source = root / "main.tex"
            contents = r"\documentclass{article}\begin{document}\notdefined\end{document}"
            source.write_text(contents)
            write_project_info(root, {"main_file": "main.tex", "pdf_file": "build/main.pdf", "arguments": []})
            output = (
                "LaTeX Warning: There were undefined references.\n"
                "main.tex:1: Undefined control sequence.\n"
                "l.1 \\notdefined\n\n"
                "Latexmk: Incomplete (and hence corrupt) bcf file 'build/main.bcf'\n"
                "Latexmk: ========== Incomplete .bcf file 'build/main.bcf'.\n"
            )
            result = subprocess.CompletedProcess([], 12, output, "")
            terminal = io.StringIO()
            with patch("ltex.build.resolve_engine", return_value=["latexmk"]), patch(
                "ltex.build.subprocess.run", return_value=result
            ) as run, redirect_stdout(terminal):
                self.assertFalse(build(root, {"engine": "latexmk", "distribution": "texlive"}))
            run.assert_called_once()
            self.assertEqual(source.read_text(), contents)
            self.assertFalse(json.loads((root / ".ltex/state.json").read_text())["success"])
            self.assertIn(r"l.1 \notdefined", terminal.getvalue())
            self.assertIn("undefined LaTeX command stopped compilation", terminal.getvalue())
            self.assertIn("an incomplete .bcf can result from LaTeX stopping early", terminal.getvalue())
            self.assertIn("Fix any source errors above, then rebuild", terminal.getvalue())
            self.assertEqual((root / ".ltex/build.log").read_text(), output + "\n")


if __name__ == "__main__":
    unittest.main()
