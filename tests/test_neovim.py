import json
import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ltex.cli import main, open_editor_at, open_path
from ltex.config import DEFAULTS
from ltex.neovim import remote_command, startup_arguments


class NeovimTests(unittest.TestCase):
    def test_project_editor_registers_its_server(self):
        with TemporaryDirectory() as directory, patch("ltex.cli.subprocess.Popen") as popen:
            root = Path(directory)
            (root / ".ltex").mkdir()
            self.assertTrue(open_path(root, "nvim --clean", "editor"))
            arguments = popen.call_args.args[0]
            self.assertEqual(arguments[:3], ["nvim", "--clean", "--cmd"])
            self.assertIn("v:servername", arguments[3])
            self.assertIn(str(root / ".ltex" / "nvim-server"), arguments[3])
            self.assertEqual(popen.call_args.kwargs, {"cwd": directory})

    def test_inverse_search_uses_registered_project(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"NVIM": ""}):
            root = Path(directory)
            (root / ".ltex").mkdir()
            (root / ".ltex" / "nvim-server").write_text("/tmp/project.sock\n")
            source = root / "chapters" / "main's <CR> file.tex"
            source.parent.mkdir()
            command = remote_command(source, 42, -1, ["nvim"])
            self.assertEqual(command[:4], ["nvim", "--server", "/tmp/project.sock", "--remote-expr"])
            self.assertIn("main''s <CR> file.tex", command[4])
            self.assertIn("cursor(42, 1)", command[4])

    def test_explicit_server_takes_priority_over_inherited_server(self):
        with patch.dict(os.environ, {"NVIM": "/tmp/inherited.sock"}):
            command = remote_command(Path("main.tex"), 1, 1, ["nvim"], "/tmp/explicit.sock")
            self.assertEqual(command[2], "/tmp/explicit.sock")

    def test_editor_command_can_specify_listen_address(self):
        with patch.dict(os.environ, {"NVIM": "/tmp/inherited.sock"}):
            command = remote_command(Path("main.tex"), 1, 1, ["nvim", "--listen", "/tmp/custom.sock"])
            self.assertEqual(command[2], "/tmp/custom.sock")

    def test_inherited_server_supports_watch_from_neovim_terminal(self):
        with patch.dict(os.environ, {"NVIM": "/tmp/inherited.sock"}):
            command = remote_command(Path("main.tex"), 1, 1, ["nvim"])
            self.assertEqual(command[2], "/tmp/inherited.sock")

    def test_callback_contacts_existing_editor_without_starting_another(self):
        result = subprocess.CompletedProcess([], 0, "", "")
        with patch("ltex.cli.subprocess.run", return_value=result) as run, patch(
            "ltex.cli.subprocess.Popen"
        ) as popen, patch("ltex.cli._config", return_value={**DEFAULTS, "editor": "nvim", "nvim_server": "/tmp/test.sock"}):
            self.assertEqual(main(["inverse-search", "main.tex", "42", "8"]), 0)
            self.assertEqual(run.call_args.args[0][:4], ["nvim", "--server", "/tmp/test.sock", "--remote-expr"])
            self.assertIn("cursor(42, 8)", run.call_args.args[0][4])
            popen.assert_not_called()

    def test_missing_server_reports_failure_without_launching_editor(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"NVIM": ""}), patch(
            "ltex.cli.subprocess.Popen"
        ) as popen, patch("ltex.cli.subprocess.run") as run:
            self.assertFalse(open_editor_at(Path(directory) / "main.tex", 1, 1, "nvim"))
            popen.assert_not_called()
            run.assert_not_called()

    def test_stale_server_reports_failure(self):
        result = subprocess.CompletedProcess([], 1, "", "connection refused")
        with patch("ltex.cli.subprocess.run", return_value=result):
            self.assertFalse(open_editor_at(Path("main.tex"), 1, 1, "nvim", nvim_server="/tmp/stale.sock"))

    def test_unresponsive_server_reports_failure(self):
        with patch("ltex.cli.subprocess.run", side_effect=subprocess.TimeoutExpired("nvim", 5)):
            self.assertFalse(open_editor_at(Path("main.tex"), 1, 1, "nvim", nvim_server="/tmp/busy.sock"))

    @unittest.skipUnless(shutil.which("nvim"), "Neovim is required for the RPC integration test")
    def test_real_neovim_receives_source_and_cursor(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"NVIM": "", "NVIM_LOG_FILE": str(Path(directory) / "nvim.log")}):
            root = Path(directory)
            (root / ".ltex").mkdir()
            source = root / "main's <CR> file.tex"
            source.write_text("first\nsecond line\nthird\n", encoding="utf-8")
            editor = subprocess.Popen(
                ["nvim", "--headless", "--clean", "-n", "-i", "NONE", *startup_arguments(root)],
                cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                registration = root / ".ltex" / "nvim-server"
                for _ in range(100):
                    if registration.exists():
                        break
                    if editor.poll() is not None:
                        self.fail(f"Neovim exited: {editor.communicate()!r}")
                    time.sleep(0.02)
                self.assertTrue(registration.exists(), "Neovim did not register its server")
                server = registration.read_text().strip()
                if not server:
                    self.skipTest("Neovim cannot create an RPC socket in this environment")
                self.assertTrue(open_editor_at(source, 2, 4, "nvim"))
                result = subprocess.run(
                    ["nvim", "--server", server, "--remote-expr", 'json_encode([expand("%:p"), line("."), col(".")])'],
                    capture_output=True, text=True, check=True, timeout=5,
                )
                self.assertEqual(json.loads(result.stdout), [str(source), 2, 4])
            finally:
                editor.terminate()
                editor.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
