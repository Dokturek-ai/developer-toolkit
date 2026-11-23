"""Tests for scripts/check_repo.py host and URL checks; synthetic text and a temporary tree only."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "check_repo", Path(__file__).resolve().parent.parent / "check_repo.py")
check_repo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_repo)

ALLOWED = "medplum.test.dokturek.ai"
# Hostile hosts are assembled at runtime so this file itself passes check_repo.py.
SUFFIX = "dokturek" + ".ai"
FOREIGN = "evil" + ".example"
LOOKALIKES = (
    ALLOWED + "." + FOREIGN,
    ALLOWED + "-" + FOREIGN,
    "x" + SUFFIX,
    "evil-" + SUFFIX,
    SUFFIX + "." + FOREIGN,
)


class DokturekHostTest(unittest.TestCase):
    def test_allowed_hosts_pass_in_any_form(self):
        texts = [
            "https://" + ALLOWED + "/mcp/stream",
            "Server " + ALLOWED + ".",
            "`" + ALLOWED.upper() + "`",
            "coolify.infra." + SUFFIX + " a app.test." + SUFFIX,
            "zástupný zápis *." + SUFFIX + " není hostitel",
        ]
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(check_repo.dokturek_host_problems(text), [])

    def test_lookalikes_report_full_host_not_allowed_prefix(self):
        for host in LOOKALIKES:
            for text in ("https://" + host + "/oauth2/token", "hostitel " + host + "."):
                with self.subTest(text=text):
                    problems = check_repo.dokturek_host_problems(text)
                    self.assertEqual(len(problems), 1)
                    self.assertIn("'{}'".format(host.lower()), problems[0])

    def test_unlisted_subdomain_is_rejected(self):
        for host in ("prod." + SUFFIX, "medplum.prod." + SUFFIX, SUFFIX):
            with self.subTest(host=host):
                problems = check_repo.dokturek_host_problems("https://" + host + "/")
                self.assertEqual(problems, ["hostitel '{}' není v allowlistu (scripts/check_repo.py)".format(host)])


class UrlTest(unittest.TestCase):
    def test_code_allows_only_listed_hosts_and_loopback(self):
        ok = [
            "https://" + ALLOWED + "/mcp/stream",
            "https://github.com/Dokturek-ai/developer-toolkit",
            "https://json.schemastore.org/claude-code-marketplace.json",
            "https://claude.ai/api/mcp/auth_callback",
            "http://127.0.0.1:1457/callback/x",
            "http://localhost:1458/callback",
        ]
        for url in ok:
            with self.subTest(url=url):
                self.assertEqual(check_repo.url_problems('"{}"'.format(url), "code"), [])
        problems = check_repo.url_problems('"https://' + FOREIGN + '/x"', "code")
        self.assertEqual(len(problems), 1)
        self.assertIn(FOREIGN, problems[0])

    def test_docs_may_link_external_https_hosts(self):
        text = "[odkaz](https://" + FOREIGN + "/page) a https://docs." + FOREIGN + "."
        self.assertEqual(check_repo.url_problems(text, "doc"), [])

    def test_plain_http_only_for_loopback_everywhere(self):
        for kind in ("code", "doc"):
            for url in ("http://" + FOREIGN + "/", "http://" + ALLOWED + "/mcp/stream",
                        "HTTP://" + FOREIGN + "/", "http://10.0.0.1/"):
                with self.subTest(kind=kind, url=url):
                    problems = check_repo.url_problems(url, kind)
                    self.assertEqual(len(problems), 1)
                    self.assertIn("http://", problems[0])

    def test_userinfo_backslash_empty_and_invalid_urls_are_rejected(self):
        for url in ("https://" + ALLOWED + "@" + FOREIGN + "/",
                    "https://user@" + ALLOWED + "/",
                    "https://" + FOREIGN + "\\@" + ALLOWED + "/",
                    "https://:443/path",
                    "https://" + ALLOWED + ":notaport/",
                    "http://[::1]:1458/callback",
                    "http://[2001:db8::1]/"):
            for kind in ("code", "doc"):
                with self.subTest(url=url, kind=kind):
                    self.assertEqual(len(check_repo.url_problems(url, kind)), 1)

    def test_bare_scheme_in_prose_is_not_a_url(self):
        for kind in ("code", "doc"):
            with self.subTest(kind=kind):
                self.assertEqual(check_repo.url_problems("jen `https`, žádné `http://` ani https://.", kind), [])

    def test_tests_skip_url_rules_but_not_dokturek_hosts(self):
        text = "https://x/scim http://" + FOREIGN + " https://" + LOOKALIKES[0] + "/"
        self.assertEqual(check_repo.url_problems(text, "test"), [])
        self.assertEqual(len(check_repo.dokturek_host_problems(text)), 1)


class TreeTest(unittest.TestCase):
    """check_hosts_and_versions walks the whole tree, not only tools/ and .claude-plugin."""

    def run_tree(self, files):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            with patch.object(check_repo, "ROOT", root), \
                    patch.object(check_repo, "SELF", root / "scripts" / "check_repo.py"), \
                    patch.object(check_repo, "errors", []) as errors:
                check_repo.check_hosts_and_versions()
            return list(errors)

    def test_kinds_by_path(self):
        errors = self.run_tree({
            "docs/guide.md": "https://" + FOREIGN + "/ok and https://" + LOOKALIKES[0] + "/bad",
            "README.md": "http://" + FOREIGN + "/",
            "scripts/tool.py": 'URL = "https://' + FOREIGN + '/api"',
            ".github/workflows/ci.yml": "run: curl https://" + FOREIGN + "/install.sh",
            "tools/x/tests/test_x.py": '"https://' + FOREIGN + '/"',
            "tools/x/config.json": '{"url": "https://' + ALLOWED + '/mcp/stream"}',
        })
        by_file = {}
        for message in errors:
            by_file.setdefault(message.split(":", 1)[0], []).append(message)
        self.assertEqual(sorted(by_file), sorted([
            "docs/guide.md", "README.md", "scripts/tool.py", ".github/workflows/ci.yml"]))
        self.assertIn("napodobuje", by_file["docs/guide.md"][0])
        self.assertEqual(len(by_file["docs/guide.md"]), 1)


if __name__ == "__main__":
    unittest.main()
