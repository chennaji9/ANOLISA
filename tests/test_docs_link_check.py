#!/usr/bin/env python3
"""Unit tests for scripts/docs-link-check.py scope and link resolution.

Run from the repository root:
    python3 tests/test_docs_link_check.py -v
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "docs-link-check.py"
_spec = importlib.util.spec_from_file_location("docs_link_check", _SCRIPT)
dlc = importlib.util.module_from_spec(_spec)
sys.modules["docs_link_check"] = dlc
_spec.loader.exec_module(dlc)


def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


class FileScopeTest(unittest.TestCase):
    def test_relocated_component_readmes_are_in_scope(self):
        """Component READMEs outside src/ must be link-checked too."""
        files = {p.relative_to(_repo_root()).as_posix() for p in dlc.files_to_check(_repo_root())}
        assert "deprecated/copilot-shell/README.md" in files
        assert "deprecated/copilot-shell/README_zh.md" in files
        assert "distribution/anolisa/README.md" in files
        assert "distribution/anolisa/README_zh.md" in files

    def test_src_component_readmes_still_in_scope(self):
        files = {p.relative_to(_repo_root()).as_posix() for p in dlc.files_to_check(_repo_root())}
        assert "src/blaze/README.md" in files
        assert "src/ws-ckpt/README.md" in files


class LinkResolutionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _check(self, markdown: str, filename: str = "page.md") -> list[str]:
        md = self.dir / filename
        md.write_text(markdown, encoding="utf-8")
        return dlc.check_file(md, self.dir)

    def test_broken_relative_link_is_flagged(self):
        errors = self._check("[docs](missing.md)")
        assert any("missing.md" in e for e in errors)

    def test_existing_link_and_skipped_targets_are_clean(self):
        (self.dir / "target.md").write_text("x", encoding="utf-8")
        errors = self._check("[ok](target.md) [ext](https://example.com) [anchor](#sec)")
        assert errors == []

    def test_relative_subdirectory_link_resolves(self):
        sub = self.dir / "sub"
        sub.mkdir()
        (self.dir / "target_root.md").write_text("x", encoding="utf-8")
        errors = self._check("[up](../target_root.md)", filename="sub/page.md")
        assert errors == []


if __name__ == "__main__":
    unittest.main()
