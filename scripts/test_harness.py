"""Run after copying the automation assets into the target's scripts directory."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import check_harness


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="harness-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "scripts").mkdir()
        (self.root / "plans/active").mkdir(parents=True)
        self.config = {
            "agents": "AGENTS.md",
            "maxAgentLines": 100,
            "activePlans": "plans/active",
            "required": ["AGENTS.md", "plans/active"],
            "markdownRoots": ["AGENTS.md"],
        }
        self.save_config()
        self.agent = self.root / "AGENTS.md"
        self.agent.write_text("# Fixture\n[Plans](plans/active/)\n", encoding="utf-8")

    def save_config(self):
        (self.root / "scripts/harness.json").write_text(json.dumps(self.config), encoding="utf-8")

    def test_valid_custom_paths_and_code_examples(self):
        self.agent.write_text(
            "[Plans](plans/active/)\n```md\n[Ignored](missing)\n```\n`[Ignored](missing)`\n",
            encoding="utf-8",
        )
        self.assertEqual(check_harness.check(self.root), [])

    def test_missing_path_broken_links_and_long_entrypoint(self):
        (self.root / "plans/active").rmdir()
        self.agent.write_text("[Broken](missing.md)\n" + "line\n" * 100, encoding="utf-8")
        errors = check_harness.check(self.root)
        self.assertTrue(any("Missing harness path" in e for e in errors))
        self.assertTrue(any("broken local link" in e for e in errors))
        self.assertTrue(any("exceeds" in e for e in errors))

    def test_reference_encoded_and_angle_links(self):
        (self.root / "a b.md").touch()
        self.agent.write_text(
            "[a](<a b.md>)\n[b](a%20b.md#title)\n[ref]: missing.md\n[web](https://example.org)\n",
            encoding="utf-8",
        )
        self.assertEqual(len(check_harness.check(self.root)), 1)

    def test_escape_and_invalid_config_fail(self):
        self.config["markdownRoots"] = ["../outside"]
        self.save_config()
        self.assertTrue(check_harness.check(self.root))
        self.config["markdownRoots"] = ["AGENTS.md"]
        self.config["maxAgentLines"] = "100"
        self.save_config()
        self.assertTrue(check_harness.check(self.root))

    def test_symlink_directory_not_traversed(self):
        (self.root / "linked").symlink_to(self.root, target_is_directory=True)
        self.config["markdownRoots"] = ["."]
        self.save_config()
        self.assertEqual(check_harness.check(self.root), [])

    def test_cli_reports_failure_and_success(self):
        shutil_source = Path(check_harness.__file__)
        entrypoint = self.root / "scripts/check_harness.py"
        entrypoint.write_text(shutil_source.read_text(encoding="utf-8"), encoding="utf-8")
        valid = subprocess.run(
            [sys.executable, str(entrypoint)], capture_output=True, text=True, check=False
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.agent.write_text("[Broken](missing.md)", encoding="utf-8")
        invalid = subprocess.run(
            [sys.executable, str(entrypoint)], capture_output=True, text=True, check=False
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("broken local link", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
