"""Exercise real hook scripts and Make dispatch without installing app dependencies."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class HookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="weft-hook-fixture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.checkout = self.root / "checkout with spaces"
        self.checkout.mkdir()
        self.log = self.root / "commands.log"
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + os.pathsep + os.defpath,
            "FIXTURE_ROOT": str(self.checkout),
            "FIXTURE_LOG": str(self.log),
            "FIXTURE_EXIT": "0",
        }
        self.executable("git", '#!/bin/sh\nprintf "%s\\n" "$FIXTURE_ROOT"\n')
        self.executable(
            "make",
            '#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" >> "$FIXTURE_LOG"\nexit "$FIXTURE_EXIT"\n',
        )

    def executable(self, name, content):
        path = self.bin / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_hooks_select_root_and_propagate_success_and_failure(self):
        for name, target in [("pre-commit", "verify-fast"), ("pre-push", "verify")]:
            hook = ROOT / ".githooks" / name
            self.assertTrue(os.access(hook, os.X_OK))
            for code in [0, 17]:
                with self.subTest(hook=name, exit_code=code):
                    self.env["FIXTURE_EXIT"] = str(code)
                    self.log.unlink(missing_ok=True)
                    result = subprocess.run(
                        [str(hook)],
                        cwd=self.root,
                        env=self.env,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(self.log.read_text().strip(), f"{self.checkout}|{target}")

    def test_full_verification_stops_before_tests_when_fast_check_fails(self):
        make = shutil.which("make")
        self.assertIsNotNone(make, "Make is required to verify the harness")
        fake_poetry = self.executable(
            "fake-poetry",
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$FIXTURE_LOG"\n'
            'case "$*" in "run ruff check .") exit "$FIXTURE_EXIT";; esac\n',
        )
        for code in [0, 9]:
            with self.subTest(exit_code=code):
                self.env["FIXTURE_EXIT"] = str(code)
                self.log.unlink(missing_ok=True)
                result = subprocess.run(
                    [make, "-f", str(ROOT / "Makefile"), f"POETRY={fake_poetry}", "verify"],
                    cwd=self.checkout,
                    env=self.env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                commands = self.log.read_text().splitlines()
                if code == 0:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        commands,
                        [
                            "run python scripts/check_harness.py",
                            "run ruff check .",
                            "run ruff format --check .",
                            "run mypy",
                            "run pytest --cov=src --cov-report=term-missing",
                        ],
                    )
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(
                        commands, ["run python scripts/check_harness.py", "run ruff check ."]
                    )


if __name__ == "__main__":
    unittest.main()
