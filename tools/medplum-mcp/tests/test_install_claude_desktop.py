"""Installer regression tests with synthetic config; no real client configuration."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "install_claude_desktop", Path(__file__).resolve().parent.parent / "scripts" / "install_claude_desktop.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTest(unittest.TestCase):
    def test_conflicting_config_does_not_print_secrets_or_write(self):
        secret = "synthetic-existing-secret"
        config = {"mcpServers": {installer.SERVER: {
            "command": "synthetic-command", "args": ["--token", secret], "env": {"API_TOKEN": secret}}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = json.dumps(config)
            path.write_text(original, encoding="utf-8")
            for flags in ([], ["--apply"]):
                with self.subTest(flags=flags):
                    output = io.StringIO()
                    with patch.object(installer, "build_entry", return_value={"command": "synthetic-new"}), \
                            patch.object(installer, "write_config") as write, \
                            patch.object(installer.sys, "argv", ["installer", "--config", str(path)] + flags), \
                            contextlib.redirect_stdout(output):
                        self.assertEqual(installer.main(), 2)
                    self.assertNotIn(secret, output.getvalue())
                    self.assertIn("--force", output.getvalue())
                    write.assert_not_called()
                    self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
