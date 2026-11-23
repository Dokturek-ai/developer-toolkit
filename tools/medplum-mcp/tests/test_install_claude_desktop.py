"""Installer regression tests with synthetic config; no real client configuration."""
import contextlib
import importlib.util
import io
import json
import os
import stat
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


ENTRY = {"command": "synthetic-npx", "args": ["synthetic-arg"]}


class InstallerFileTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def run_installer(self, path, *flags):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(installer, "build_entry", return_value=dict(ENTRY)), \
                patch.object(installer, "desktop_running", return_value=False), \
                patch.object(installer.sys, "argv", ["installer", "--config", str(path)] + list(flags)), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = installer.main()
        return code, output.getvalue(), errors.getvalue()

    def mode(self, path):
        return stat.S_IMODE(os.stat(str(path)).st_mode)

    def test_malformed_or_non_object_json_fails_cleanly_without_writing(self):
        secret = "synthetic-secret-in-broken-config"
        bodies = ['{"mcpServers": {"x": {"env": {"T": "' + secret + '"}}', "[]", "null", '"text"', "42",
                  '{"mcpServers": []}', '{"mcpServers": "' + secret + '"}', "\xff\xfe"]
        for body in bodies:
            for flags in ([], ["--apply"], ["--remove", "--apply"]):
                with self.subTest(body=body, flags=flags):
                    path = self.dir / "config.json"
                    path.write_bytes(body.encode("latin-1") if body == "\xff\xfe" else body.encode("utf-8"))
                    before = path.read_bytes()
                    code, output, errors = self.run_installer(path, *flags)
                    self.assertEqual(code, 4)
                    self.assertIn("Chyba:", errors)
                    self.assertIn("Nic se nezměnilo", errors)
                    self.assertNotIn(secret, output + errors)
                    self.assertNotIn("Traceback", output + errors)
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["config.json"])

    def test_new_config_is_written_with_0600(self):
        path = self.dir / "Claude" / "config.json"
        code, _, _ = self.run_installer(path, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                         {"mcpServers": {installer.SERVER: ENTRY}})
        self.assertEqual(self.mode(path), 0o600)

    def test_existing_config_and_backup_end_up_0600_and_other_keys_survive(self):
        path = self.dir / "config.json"
        path.write_text(json.dumps({"other": {"keep": True}}), encoding="utf-8")
        os.chmod(str(path), 0o644)
        code, _, _ = self.run_installer(path, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                         {"other": {"keep": True}, "mcpServers": {installer.SERVER: ENTRY}})
        self.assertEqual(self.mode(path), 0o600)
        backups = [p for p in self.dir.iterdir() if ".bak-" in p.name]
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.mode(backups[0]), 0o600)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), {"other": {"keep": True}})

    def test_symlinked_config_is_written_through_and_link_preserved(self):
        real_dir = self.dir / "dotfiles"
        real_dir.mkdir()
        target = real_dir / "claude_desktop_config.json"
        target.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        link = self.dir / "config.json"
        os.symlink(os.path.relpath(str(target), str(self.dir)), str(link))
        for flags, expected in ((["--apply"], {installer.SERVER: ENTRY}), (["--remove", "--apply"], {})):
            with self.subTest(flags=flags):
                code, output, _ = self.run_installer(link, *flags)
                self.assertEqual(code, 0)
                self.assertTrue(link.is_symlink())
                self.assertEqual(os.path.realpath(str(link)), os.path.realpath(str(target)))
                self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["mcpServers"], expected)
                self.assertEqual(self.mode(target), 0o600)
                self.assertIn("symlink", output)
        self.assertEqual([p.name for p in self.dir.iterdir() if ".bak-" in p.name], [])
        self.assertTrue(any(".bak-" in p.name for p in real_dir.iterdir()))

    def test_dangling_symlink_is_refused(self):
        link = self.dir / "config.json"
        os.symlink(str(self.dir / "missing" / "config.json"), str(link))
        for flags in ([], ["--apply"]):
            with self.subTest(flags=flags):
                code, _, errors = self.run_installer(link, *flags)
                self.assertEqual(code, 4)
                self.assertIn("symlink", errors)
                self.assertTrue(link.is_symlink())
                self.assertFalse((self.dir / "missing").exists())


if __name__ == "__main__":
    unittest.main()
