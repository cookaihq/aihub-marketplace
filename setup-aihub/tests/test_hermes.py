"""Offline Hermes profile boundaries; native-session evidence is recorded separately."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_setup import MARKET
from setup_core.consumers import Consumer, host_context, path_id
from setup_core.errors import SetupError
from setup_core.progress import Tasks, guard_context


class HermesContextTests(unittest.TestCase):
    def test_resume_and_listing_are_bound_to_the_active_profile(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            root = Path(temporary)
            with patch("pathlib.Path.home", return_value=root), patch.dict(os.environ, {"HERMES_HOME": str(root / "first")}):
                consumer = Consumer("aihub-studio", MARKET / "aihub-studio", "aihub-image", root)
                context = consumer.context("hermes")
                tasks = Tasks()
                state = tasks.start(context, "configure", "manual", "installed", "not_submitted")
                guard_context(state, "hermes", root)
                self.assertEqual(len(tasks.matches("hermes", root)), 1)
                with patch.dict(os.environ, {"HERMES_HOME": str(root / "second")}):
                    with self.assertRaises(SetupError) as error:
                        guard_context(state, "hermes", root)
                    self.assertEqual(error.exception.reason, "task_context_mismatch")
                    self.assertEqual(tasks.matches("hermes", root), [])
                with self.assertRaises(SetupError):
                    guard_context(state, "codex", root)
                self.assertNotIn("hermes_home", consumer.context("codex"))

    def test_platform_default_and_suffix(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
            root = Path(temporary)
            with patch("pathlib.Path.home", return_value=root), patch.dict(os.environ, {"HERMES_HOME": "", "LOCALAPPDATA": str(root / "local"), "HERMES_DATA_DIR_SUFFIX": "-dev"}):
                expected = root / "local/hermes-dev" if os.name == "nt" else root / ".hermes-dev"
                self.assertEqual(host_context("hermes"), {"hermes_home": path_id(expected.resolve())})
                with patch.dict(os.environ, {"HERMES_HOME": "${HERMES_TEST_PROFILE}", "HERMES_TEST_PROFILE": str(expected)}):
                    self.assertEqual(host_context("hermes"), {"hermes_home": path_id(expected.resolve())})


if __name__ == "__main__":
    unittest.main()
