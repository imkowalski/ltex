import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ltex.build import missing_miktex_packages, project_arguments, resolve_engine
from ltex.cli import open_path
from ltex.project import find_main_file, main_file_path, metadata_path, project_info, write_project_info


class EngineResolutionTests(unittest.TestCase):
    def test_uses_standard_engine_name(self):
        with patch("ltex.build.shutil.which", side_effect=lambda name: name if name == "pdflatex" else None):
            self.assertEqual(resolve_engine(["pdflatex"], "miktex"), ["pdflatex"])

    def test_uses_miktex_prefixed_latex_engine_name(self):
        with patch("ltex.build.shutil.which", side_effect=lambda name: name if name == "miktex-pdflatex" else None):
            self.assertEqual(resolve_engine(["pdflatex"], "miktex"), ["miktex-pdflatex"])

    def test_uses_miktex_pdftex_with_latex_format(self):
        with patch("ltex.build.shutil.which", side_effect=lambda name: name if name == "miktex-pdftex" else None):
            self.assertEqual(resolve_engine(["pdflatex"], "miktex"), ["miktex-pdftex", "-fmt=pdflatex"])

    def test_does_not_use_miktex_fallback_for_other_distributions(self):
        with patch("ltex.build.shutil.which", side_effect=lambda name: name if name == "miktex" else None):
            self.assertIsNone(resolve_engine(["pdflatex"], "texlive"))


class MainFileDetectionTests(unittest.TestCase):
    def test_prefers_nested_main_tex_over_alphabetic_section_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "0-Config.tex").write_text(r"\setTitle{Example}\n", encoding="utf-8")
            entrypoint = root / "setup-things" / "main.tex"
            entrypoint.parent.mkdir()
            entrypoint.write_text(r"\input{setup-things/preamble}\n\begin{document}\n\end{document}", encoding="utf-8")
            self.assertEqual(find_main_file(root), entrypoint)

    def test_repairs_metadata_that_points_to_a_section_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            section = root / "0-Config.tex"
            section.write_text(r"\setTitle{Example}", encoding="utf-8")
            entrypoint = root / "setup-things" / "main.tex"
            entrypoint.parent.mkdir()
            entrypoint.write_text(r"\begin{document}\n\end{document}", encoding="utf-8")
            self.assertEqual(main_file_path(root, {"main_file": "0-Config.tex"}), entrypoint)

    def test_new_metadata_is_written_in_project_root(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".ltex").mkdir()
            write_project_info(root, {"main_file": "main.tex", "pdf_file": "build/main.pdf", "arguments": []})
            self.assertEqual(metadata_path(root), root / "project.json")
            self.assertEqual(project_info(root)["arguments"], [])

    def test_project_arguments_accepts_extra_flags(self):
        self.assertEqual(project_arguments({"arguments": ["-shell-escape"]}), ["-shell-escape"])
        self.assertEqual(project_arguments({"arguments": "-shell-escape"}), [])

    def test_missing_package_names_are_detected(self):
        output = "! LaTeX Error: File `makecell.sty' not found.\n! LaTeX Error: File `foo.cls' not found."
        self.assertEqual(missing_miktex_packages(output), ["makecell", "foo"])

    def test_terminal_editor_opens_project_as_working_directory(self):
        with TemporaryDirectory() as directory, patch("ltex.cli.subprocess.Popen") as popen:
            self.assertTrue(open_path(Path(directory), "nvim", "editor"))
            popen.assert_called_once_with(["nvim"], cwd=directory)


if __name__ == "__main__":
    unittest.main()
