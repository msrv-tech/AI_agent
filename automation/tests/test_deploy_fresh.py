# -*- coding: utf-8 -*-
"""Unit tests for Fresh deploy helpers. Live 1C:Fresh upload is not invoked here."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from automation.fresh.common import (
    changelog_from_release_notes,
    file_sha256,
    fresh_cfe_name,
    read_extension_version,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class FreshDeployHelpersTests(unittest.TestCase):
    def test_read_current_extension_version(self) -> None:
        version = read_extension_version(REPO_ROOT / "xml" / "Configuration.xml")
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_fresh_cfe_name(self) -> None:
        self.assertEqual(fresh_cfe_name("0.9.9"), "AI_Agent_Fresh_0.9.9.cfe")

    def test_changelog_from_current_release_notes(self) -> None:
        version = read_extension_version(REPO_ROOT / "xml" / "Configuration.xml")
        notes = REPO_ROOT / "docs" / "releases" / f"v{version}.md"
        text = changelog_from_release_notes(notes)
        self.assertIn("- ", text)
        self.assertNotIn("## Главное", text)

    def test_missing_release_notes_are_an_error(self) -> None:
        with self.assertRaises(RuntimeError):
            changelog_from_release_notes(REPO_ROOT / "docs" / "releases" / "v0.0.0.md")

    def test_file_sha256(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"fresh-cfe")
            path = Path(handle.name)
        try:
            digest = file_sha256(path)
            self.assertEqual(len(digest), 64)
            self.assertEqual(digest, file_sha256(path))
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
