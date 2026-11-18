import importlib.util
import unittest
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ltex.cli import watch
from ltex.project import write_project_info


@unittest.skipUnless(importlib.util.find_spec("watchdog"), "watchdog is required for watcher tests")
class WatchEventsTests(unittest.TestCase):
    def test_reads_do_not_queue_builds_but_saves_and_atomic_replacements_do(self):
        from watchdog.events import FileOpenedEvent, FileClosedNoWriteEvent, FileModifiedEvent, FileMovedEvent

        for event_type in (FileOpenedEvent, FileClosedNoWriteEvent, FileModifiedEvent, FileMovedEvent):
            with self.subTest(event_type=event_type.__name__), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".ltex").mkdir()
                source = root / "main.tex"
                source.write_text(r"\documentclass{article}\begin{document}\end{document}")
                write_project_info(root, {"main_file": "main.tex", "pdf_file": "build/main.pdf", "arguments": []})
                changes = Queue()
                with patch("watchdog.observers.Observer") as observer_type, patch(
                    "ltex.cli.Queue", return_value=changes
                ), patch.object(changes, "get", side_effect=KeyboardInterrupt), patch(
                    "ltex.cli.project_needs_build", return_value=False
                ), patch("ltex.cli.build") as build:
                    observer = observer_type.return_value

                    def deliver_event():
                        handler = observer.schedule.call_args.args[0]
                        event = (
                            FileMovedEvent(str(root / "save.tmp"), str(source))
                            if event_type is FileMovedEvent else event_type(str(source))
                        )
                        handler.dispatch(event)

                    observer.start.side_effect = deliver_event
                    self.assertEqual(watch(root, {}, viewer=False), 0)
                    build.assert_not_called()
                    observer.stop.assert_called_once()
                    observer.join.assert_called_once()
                self.assertEqual(changes.qsize(), int(event_type in (FileModifiedEvent, FileMovedEvent)))
                if not changes.empty():
                    self.assertEqual(changes.get_nowait(), source)


if __name__ == "__main__":
    unittest.main()
