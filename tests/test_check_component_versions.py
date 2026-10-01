#!/usr/bin/env python3
"""Unit tests for scripts/check-component-versions.py TOML version reading.

Run from the repository root:
    python3 tests/test_check_component_versions.py -v
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-component-versions.py"
_spec = importlib.util.spec_from_file_location("check_component_versions", _SCRIPT)
ccv = importlib.util.module_from_spec(_spec)
sys.modules["check_component_versions"] = ccv
_spec.loader.exec_module(ccv)


class ReadTomlVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _read(self, content: str) -> str:
        path = os.path.join(self.tmp.name, "probe.toml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return ccv.read_toml_version(path)

    def test_package_section(self):
        assert self._read('[package]\nname = "x"\nversion = "1.2.3"\n') == "1.2.3"

    def test_workspace_package_section(self):
        content = (
            "[workspace]\nmembers = [\"crates/*\"]\n\n"
            "[workspace.package]\nversion = \"0.26.0\"\n"
        )
        assert self._read(content) == "0.26.0"

    def test_component_section(self):
        content = (
            'manifest_version = 2\n\n[component]\nname = "os-skills"\nversion = "0.6.3"\n'
        )
        assert self._read(content) == "0.6.3"

    def test_top_level_version(self):
        assert self._read('version = "9.9.9"\n') == "9.9.9"

    def test_dependency_versions_do_not_satisfy_the_lookup(self):
        content = (
            "[workspace.package]\nversion = \"0.5.0\"\n\n"
            "[workspace.dependencies]\nserde = { version = \"1.0\" }\n"
        )
        assert self._read(content) == "0.5.0"

    def test_only_a_dependency_version_is_rejected(self):
        content = "[dependencies]\nserde = { version = \"1.0\" }\n"
        with self.assertRaises(ValueError):
            self._read(content)

    def test_malformed_toml_is_rejected_even_with_a_version_line(self):
        # A syntax error anywhere in the file used to be swallowed and the
        # version line matched by regex, greenlighting broken metadata.
        content = '[package]\nversion = "1.2.3"\nthis is not toml {{{\n'
        with self.assertRaises(ValueError) as ctx:
            self._read(content)
        assert "malformed TOML" in str(ctx.exception)

    def test_missing_version_is_rejected(self):
        with self.assertRaises(ValueError):
            self._read('[package]\nname = "x"\n')

    def test_pre_311_fallback_still_matches_line(self):
        content = '[package]\nversion = "1.2.3"\n'
        path = os.path.join(self.tmp.name, "fallback.toml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        saved = ccv.tomllib
        ccv.tomllib = None
        try:
            assert ccv.read_toml_version(path) == "1.2.3"
        finally:
            ccv.tomllib = saved


class LiveContractsTest(unittest.TestCase):
    """The repository's own contracts still read through the structural path."""

    def test_all_toml_contracts_parse(self):
        for source, target in ccv.TOML_CONTRACTS:
            ccv.read_version(source)
            ccv.read_version(target)


if __name__ == "__main__":
    unittest.main()
