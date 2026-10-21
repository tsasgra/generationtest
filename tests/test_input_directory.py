from pathlib import Path
import tempfile
import unittest

from polygon_tool.input import PART_FILES, init_directory, parse_problem
from polygon_tool.workflow import digest


EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'a_plus_b'


class DirectoryInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'problem'
        init_directory(self.path)
        for filename in PART_FILES.values():
            (self.path / filename).write_bytes((EXAMPLE / filename).read_bytes())

    def test_ten_raw_files_map_to_exact_parts_without_markers(self):
        parts = parse_problem(self.path)
        self.assertEqual(set(parts), set(PART_FILES))
        for part, name in PART_FILES.items():
            self.assertEqual(parts[part], (self.path / name).read_bytes().decode('utf-8'))
        self.assertEqual(parts['name'], 'Tổng hai số')
        self.assertNotEqual(parts['name problem'], parts['name'])

    def test_missing_file_even_empty_note_is_reported(self):
        (self.path / 'note.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'Thiếu.*note.txt'):
            parse_problem(self.path)

    def test_empty_note_is_allowed_but_empty_source_is_rejected(self):
        (self.path / 'note.txt').write_bytes(b' \r\n\t')
        self.assertEqual(parse_problem(self.path)['note'], '')
        (self.path / 'gen.txt').write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'gen.txt.*trống'):
            parse_problem(self.path)

    def test_bom_unicode_latex_crlf_and_boundary_whitespace_are_preserved(self):
        value = '\r\n  Tiếng Việt $a \\le b$ ~ \\\\ \r\n\r\n'
        for name in ('lengend.txt', 'input.txt', 'output.txt', 'note.txt',
                     'checker.txt', 'gen.txt', 'script_sinh_test.txt', 'solution.txt'):
            (self.path / name).write_bytes(b'\xef\xbb\xbf' + value.encode())
        parts = parse_problem(self.path)
        for part in ('lengend', 'input', 'output', 'note', 'checker', 'gen', 'script_sinh_test', 'solution'):
            self.assertEqual(parts[part], value)

    def test_one_terminal_newline_allowed_in_names_only(self):
        (self.path / 'name problem.txt').write_bytes(b'sum-demo\r\n')
        (self.path / 'name.txt').write_bytes('Tổng hai số\n'.encode())
        parts = parse_problem(self.path)
        self.assertEqual(parts['name problem'], 'sum-demo')
        self.assertEqual(parts['name'], 'Tổng hai số')
        (self.path / 'name.txt').write_bytes('Tổng\n\n'.encode())
        with self.assertRaisesRegex(ValueError, 'một dòng'):
            parse_problem(self.path)

    def test_alias_allowed_but_both_spellings_rejected(self):
        (self.path / 'lengend.txt').rename(self.path / 'legend.txt')
        self.assertIn('lengend', parse_problem(self.path))
        (self.path / 'lengend.txt').write_text('duplicate')
        with self.assertRaisesRegex(ValueError, 'Trùng'):
            parse_problem(self.path)

    def test_extra_txt_rejected(self):
        (self.path / 'extra.txt').write_text('wrong input')
        with self.assertRaisesRegex(ValueError, 'đúng 10.*extra.txt'):
            parse_problem(self.path)

    def test_invalid_encoding_names_exact_file(self):
        (self.path / 'solution.txt').write_bytes(b'\xff')
        with self.assertRaisesRegex(ValueError, 'solution.txt.*UTF-8'):
            parse_problem(self.path)

    def test_outer_fence_unwrapped_and_marker_like_content_kept(self):
        (self.path / 'solution.txt').write_bytes(b'```cpp\nint main() {}\n```\n')
        (self.path / 'note.txt').write_text('<<<PART: note>>>\nLiteral content\n')
        parts = parse_problem(self.path)
        self.assertEqual(parts['solution'], 'int main() {}')
        self.assertEqual(parts['note'], '<<<PART: note>>>\nLiteral content\n')

    def test_single_file_edit_changes_checkpoint_digest(self):
        before = digest(parse_problem(self.path))
        with (self.path / 'gen.txt').open('ab') as stream:
            stream.write(b'\n// user correction\n')
        self.assertNotEqual(before, digest(parse_problem(self.path)))


if __name__ == '__main__':
    unittest.main()
