from pathlib import Path
import tempfile
import unittest

from polygon_tool.input import PARTS, parse_problem, parse_text, template


def document(overrides=None, newline="\n"):
    values = {
        "name problem": "sum-two-numbers-2026",
        "name": "Tổng hai số",
        "lengend": "Một dòng đầu.\n\nGiữ $a \\le b$ và ~ cùng \\\\.",
        "input": "Hai số nguyên.",
        "output": "Tổng hai số.",
        "note": "",
        "checker": '#include "testlib.h"\nint main() { return 0; }',
        "gen": '#include <iostream>\nint main() { std::cout << "2 3\\n"; }',
        "script_sinh_test": "gen sample 1 > $\n<#list 1..3 as i>\ngen random ${i} > $\n</#list>",
        "solution": "#include <iostream>\nint main() { return 0; }",
    }
    values.update(overrides or {})
    text = "\n\n".join(f"<<<PART: {part}>>>\n{values[part]}" for part in PARTS) + "\n"
    return text.replace("\n", newline)


class InputTests(unittest.TestCase):
    def test_empty_note_is_empty_and_names_independent(self):
        parts = parse_text(document())
        self.assertEqual(parts["note"], "")
        self.assertEqual(parts["name"], "Tổng hai số")
        self.assertEqual(parts["name problem"], "sum-two-numbers-2026")

    def test_unicode_latex_cpp_and_freemarker_unchanged(self):
        content = "  Tiếng Việt $x \\le 10^9$ ~ \\\\  \r\n\r\n\tDòng kế: \\frac{a}{b}  "
        parts = parse_text(document({"lengend": content}))
        self.assertEqual(parts["lengend"], content)
        self.assertIn("${i} > $", parts["script_sinh_test"])
        self.assertIn('"2 3\\n"', parts["gen"])

    def test_utf8_bom_crlf_is_preserved(self):
        data = document(newline="\r\n")
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "problem.txt"
            file.write_bytes(b"\xef\xbb\xbf" + data.encode("utf-8"))
            parts = parse_problem(file)
        self.assertEqual(parts["lengend"], "Một dòng đầu.\r\n\r\nGiữ $a \\le b$ và ~ cùng \\\\.")

    def test_invalid_encoding_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "bad.txt"
            file.write_bytes(b"\xff")
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                parse_problem(file)

    def test_missing_marker(self):
        with self.assertRaisesRegex(ValueError, "Thiếu phần: note"):
            parse_text(document().replace("<<<PART: note>>>\n\n", ""))

    def test_duplicate_marker(self):
        with self.assertRaisesRegex(ValueError, "Trùng phần"):
            parse_text(document() + "\n<<<PART: note>>>\n")

    def test_legend_alias(self):
        self.assertIn("lengend", parse_text(document().replace("PART: lengend", "PART: legend")))
        with self.assertRaisesRegex(ValueError, "Trùng phần"):
            parse_text(document() + "\n<<<PART: legend>>>\nExtra\n")

    def test_unknown_and_malformed_markers(self):
        for marker in ("<<<PART: alien>>>", " <<<PART: name>>>", "<<<PART: name>>"):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                parse_text(document().replace("<<<PART: name>>>", marker))

    def test_empty_required_section(self):
        with self.assertRaisesRegex(ValueError, "'gen'.*trống"):
            parse_text(document({"gen": " \t"}))

    def test_blank_note_normalizes_to_empty(self):
        self.assertEqual(parse_text(document({"note": " \t\n\t"}))["note"], "")

    def test_complete_outer_fence_unwrapped_only_once(self):
        body = "#include <iostream>\n\nint main() { return 0; }"
        self.assertEqual(parse_text(document({"solution": "```cpp\n" + body + "\n```"}))["solution"], body)
        self.assertEqual(parse_text(document({"note": "```text\n\n```"}))["note"], "")

    def test_ambiguous_fence_is_not_removed(self):
        value = "```cpp\nfirst\n```\nsecond\n```"
        self.assertEqual(parse_text(document({"solution": value}))["solution"], value)

    def test_invalid_slug_never_renamed(self):
        for slug in ("Sum", "two numbers", "bài-tập", "sum_two"):
            with self.subTest(slug=slug), self.assertRaisesRegex(ValueError, "name problem"):
                parse_text(document({"name problem": slug}))

    def test_local_slug_check_does_not_invent_dash_position_rules(self):
        for slug in ("-sum", "sum-", "sum--two"):
            with self.subTest(slug=slug):
                self.assertEqual(parse_text(document({"name problem": slug}))["name problem"], slug)

    def test_multiline_display_name_rejected(self):
        for separator in ("\n", "\r", "\u2028", "\u2029"):
            with self.subTest(separator=separator), self.assertRaisesRegex(ValueError, "một dòng"):
                parse_text(document({"name": "Tổng" + separator + "hai số"}))

    def test_preamble_rejected(self):
        with self.assertRaisesRegex(ValueError, "trước marker"):
            parse_text("Some text\n" + document())

    def test_template_has_exact_required_markers_and_is_blank(self):
        self.assertEqual(template().count("<<<PART: "), 10)
        with self.assertRaisesRegex(ValueError, "không được để trống"):
            parse_text(template())

    def test_example_parses(self):
        file = Path(__file__).resolve().parents[1] / "examples" / "a_plus_b.txt"
        parts = parse_problem(file)
        self.assertEqual(parts["name"], "Tổng hai số")
        self.assertIn("gen sample 1 > $", parts["script_sinh_test"])


if __name__ == "__main__":
    unittest.main()
