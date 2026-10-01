#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Regression tests for read_pdf.py output bounding.

Run from this directory:
    python3 -m unittest test_read_pdf -v

The unit tests need only the standard library. The end-to-end test needs
PyMuPDF and is skipped when it is not installed.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import read_pdf  # noqa: E402

try:
    import pymupdf  # noqa: F401

    HAVE_FITZ = True
except ImportError:
    try:
        import fitz  # noqa: F401

        HAVE_FITZ = True
    except ImportError:
        HAVE_FITZ = False


class CapPagesTextTest(unittest.TestCase):
    def test_under_limit_is_untouched(self):
        pages = [{"page": 1, "text": "abc"}, {"page": 2, "text": "de"}]
        self.assertFalse(read_pdf.cap_pages_text(pages, 10))
        self.assertEqual([p["text"] for p in pages], ["abc", "de"])

    def test_boundary_page_keeps_prefix_and_marker(self):
        pages = [{"page": 1, "text": "abcdefgh"}]
        self.assertTrue(read_pdf.cap_pages_text(pages, 3))
        self.assertEqual(pages[0]["text"], "abc...")

    def test_later_pages_reduce_to_marker(self):
        pages = [
            {"page": 1, "text": "abcdef"},
            {"page": 2, "text": "ghijkl"},
            {"page": 3, "text": ""},
        ]
        self.assertTrue(read_pdf.cap_pages_text(pages, 4))
        self.assertEqual(pages[0]["text"], "abcd...")
        self.assertEqual(pages[1]["text"], "...")
        self.assertEqual(pages[2]["text"], "", "empty pages stay empty")

    def test_exact_fit_is_not_trimmed(self):
        pages = [{"page": 1, "text": "abcdef"}]
        self.assertFalse(read_pdf.cap_pages_text(pages, 6))
        self.assertEqual(pages[0]["text"], "abcdef")


@unittest.skipUnless(HAVE_FITZ, "PyMuPDF not installed")
class EndToEndJsonTest(unittest.TestCase):
    def test_json_output_stays_parseable_under_max_length(self):
        import pymupdf as fitz

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "long.pdf")
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Hello PDF world " * 50)
            doc.save(pdf_path)
            doc.close()

            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "read_pdf.py")
            out = subprocess.run(
                [sys.executable, script, "-f", pdf_path, "--format", "json", "-m", "40"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout

            data = json.loads(out)
            self.assertEqual(data["total_pages"], 1)
            self.assertTrue(data.get("truncated"), "truncation must be signalled")
            self.assertLessEqual(len(data["pages"][0]["text"]), 43)

    def test_json_output_without_limit_not_truncated(self):
        import pymupdf as fitz

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "short.pdf")
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "tiny")
            doc.save(pdf_path)
            doc.close()

            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "read_pdf.py")
            out = subprocess.run(
                [sys.executable, script, "-f", pdf_path, "--format", "json"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout

            data = json.loads(out)
            self.assertNotIn("truncated", data)
            self.assertIn("tiny", data["pages"][0]["text"])


if __name__ == "__main__":
    unittest.main()
