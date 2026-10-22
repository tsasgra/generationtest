"""Offline regression checks: python -m unittest -v test_gemini_export."""
from __future__ import annotations

import html
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from gemini_export import (
    DOM_RESPONSES, PARTS, PART_FILES, _conversation_key, main, parse_response, parts_from_events,
    validate_gemini_url, write_parts,
)


def read_export(directory: Path) -> dict[str, str]:
    return {part: (directory / filename).read_bytes().decode("utf-8")
            for part, filename in PART_FILES.items()}


def sample_parts() -> dict[str, str]:
    return dict(zip(PARTS, [
        "intamgiacsaonguoc", "In Tam Giác Sao Ngược",
        "Cho một số nguyên $a$.\n\nIn \\texttt{*} với $1 \\le a \\le 1000$.",
        "Dữ liệu vào gồm số nguyên $a$.", "In tam giác gồm $a$ dòng.", "",
        '#include "testlib.h"\nint main() {\n    return 0;  \n}',
        '#include <bits/stdc++.h>\nint main() { std::cout << "5\\n"; }',
        "gen sample 1 1 > $\n<#list 1..5 as i>\ngen random 10 small solvable ${i} > $\n</#list>",
        '#include <bits/stdc++.h>\nint main() {\n    std::cout << "*\\n";\n}',
    ]))


def markdown(parts: dict[str, str], newline: str = "\n") -> str:
    return newline.join(
        f"### **Part {i}: {name}**{newline}{newline}```plaintext{newline}"
        + parts[name].replace("\n", newline) + f"{newline}```{newline}"
        for i, name in enumerate(PARTS, 1)
    )


class ExportTests(unittest.TestCase):
    def test_markdown_preserves_content_and_empty_note(self):
        expected = sample_parts()
        expected["solution"] += "\n// Part 1: this is inside code\n\n"
        self.assertEqual(parse_response("\ufeffIntroduction\n" + markdown(expected)), expected)

    def test_plain_headings_long_fences_and_crlf(self):
        expected = sample_parts()
        source = markdown(expected, "\r\n").replace("### **Part", "Part").replace("**", "")
        source = source.replace("```", "~~~~")
        actual = parse_response(source)
        self.assertEqual(actual, {k: v.replace("\n", "\r\n") for k, v in expected.items()})

    def test_missing_duplicate_empty_multiple_and_unclosed_blocks(self):
        source = markdown(sample_parts())
        broken = [
            source[:source.index("### **Part 10:")],
            source + "\nPart 1: duplicate\n```\nother\n```\n",
            source.replace("intamgiacsaonguoc", ""),
            source + "\n```cpp\nsecond solution\n```\n",
            source.rsplit("```", 1)[0],
            source.replace("Part 10:", "Part 11:"),
        ]
        for value in broken:
            with self.subTest(value=value[-70:]), self.assertRaises(ValueError):
                parse_response(value)

    def test_name_is_copied_without_upload_rules(self):
        parts = sample_parts()
        parts["name problem"] = "Tên bài có dấu và khoảng trắng"
        self.assertEqual(parse_response(markdown(parts)), parts)

    def test_write_exact_ten_files(self):
        parts = sample_parts()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "problem"
            write_parts(parts, output)
            self.assertEqual(sorted(p.name for p in output.iterdir()), sorted(PART_FILES.values()))
            for name, filename in PART_FILES.items():
                self.assertEqual((output / filename).read_bytes(), parts[name].encode("utf-8"))
            self.assertEqual(read_export(output), parts)
            with self.assertRaises(ValueError):
                write_parts(parts, output)
            parts["name"] = "Tên mới"
            write_parts(parts, output, overwrite=True)
            self.assertEqual(read_export(output), parts)

    def test_reject_foreign_files_and_restore_if_publish_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "problem"
            write_parts(sample_parts(), output)
            (output / "keep.bin").write_bytes(b"keep")
            with self.assertRaises(ValueError):
                write_parts(sample_parts(), output, overwrite=True)
            (output / "keep.bin").unlink()
            original_rename = Path.rename

            def fail_publish(path, target):
                if path.name == "new":
                    raise OSError("simulated disk error")
                return original_rename(path, target)

            with patch.object(Path, "rename", fail_publish), self.assertRaises(OSError):
                write_parts(sample_parts(), output, overwrite=True)
            self.assertEqual(read_export(output), sample_parts())

    def test_cli_invalid_response_does_not_modify_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "problem"
            write_parts(sample_parts(), output)
            source = Path(temporary) / "response.md"
            source.write_text("Part 1: incomplete", encoding="utf-8")
            self.assertEqual(main(["--from-file", str(source), "--output", str(output), "--overwrite"]), 1)
            self.assertEqual(read_export(output), sample_parts())

    def test_failed_rollback_retains_previous_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "problem"
            write_parts(sample_parts(), output)
            original_rename = Path.rename

            def fail_publish_and_restore(path, target):
                if path.name in ("new", "previous"):
                    raise OSError("simulated external lock")
                return original_rename(path, target)

            with patch.object(Path, "rename", fail_publish_and_restore), self.assertRaises(OSError):
                write_parts(sample_parts(), output, overwrite=True)
            backups = list(Path(temporary).glob(".gemini-export-*/previous"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(read_export(backups[0]), sample_parts())

    def test_url_identity_after_google_account_redirect(self):
        self.assertEqual(_conversation_key("https://gemini.google.com/app/abc123"),
                         _conversation_key("https://gemini.google.com/u/1/app/abc123?hl=vi"))
        for value in ["http://gemini.google.com/app/abc", "https://evil.test/app/abc",
                      "https://gemini.google.com.evil.test/app/abc", "https://gemini.google.com/app/"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_gemini_url(value)


class BrowserExtractionTests(unittest.TestCase):
    def test_rendered_responses_preserve_code_and_reject_newer_partial_answer(self):
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except ImportError:
            self.skipTest("Playwright not installed")
        parts = sample_parts()
        content = "<model-response>" + "".join(
            f"<p><strong>Part {i}: {name}</strong></p>"
            f"<code-block><header>Plaintext Copy Download</header><pre><code>"
            f"<span>{html.escape(parts[name])}</span></code></pre></code-block>"
            for i, name in enumerate(PARTS, 1)
        ) + "</model-response>"
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            except PlaywrightError as exc:
                self.skipTest(f"Chromium unavailable: {exc}")
            try:
                page = browser.new_page()
                page.set_content(content)
                responses = page.evaluate(DOM_RESPONSES)
                self.assertEqual(parts_from_events(responses[-1]), parts)
                page.set_content(content + "<model-response><p>Part 1: New answer</p>"
                                 "<pre><code>newslug</code></pre></model-response>")
                with self.assertRaises(ValueError):
                    parts_from_events(page.evaluate(DOM_RESPONSES)[-1])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
