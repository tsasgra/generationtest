import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import polygon_upload
from polygon_tool.input import PART_FILES, init_directory


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.input_path = Path(self.temp.name) / 'problem'
        init_directory(self.input_path)
        for part, filename in PART_FILES.items():
            value = 'test-problem' if part == 'name problem' else 'Nội dung kiểm thử'
            (self.input_path / filename).write_text(value, encoding='utf-8')

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = polygon_upload.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_offline_without_credentials_or_state(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True), patch.object(
                polygon_upload, 'PolygonAPI', side_effect=AssertionError('Network forbidden')):
            state = Path(d) / 'state.json'
            code, out, err = self.invoke(['run', '--input', str(self.input_path),
                                          '--dry-run', '--state', str(state)])
            self.assertEqual(code, 0, err)
            self.assertTrue(json.loads(out)['valid'])
            self.assertFalse(state.exists())
            self.assertFalse(state.with_name('state.json.lock').exists())

    def test_init_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'problem'
            self.assertEqual(self.invoke(['init', '--output', str(path)])[0], 0)
            self.assertEqual(len(list(path.glob('*.txt'))), 10)
            (path / 'gen.txt').write_text('user generator', encoding='utf-8')
            original = {f.name: f.read_bytes() for f in path.iterdir()}
            self.assertEqual(self.invoke(['init', '--output', str(path)])[0], 1)
            self.assertEqual({f.name: f.read_bytes() for f in path.iterdir()}, original)

    def test_invalid_limits_rejected_before_network(self):
        with patch.object(polygon_upload, 'PolygonAPI', side_effect=AssertionError('Network forbidden')):
            for args in (['--time-limit', '251'], ['--memory-limit', '1025'],
                         ['--input-file', 'same', '--output-file', 'SAME']):
                code, _, _ = self.invoke(['run', '--input', str(self.input_path), '--dry-run', *args])
                self.assertEqual(code, 1)

    def test_url_only_failure_stdout_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            code, out, err = self.invoke(['run', '--input', str(self.input_path), '--url-only'])
            self.assertEqual(code, 1)
            self.assertEqual(out, '')
            self.assertIn('POLYGON_API_KEY', err)

    def test_url_only_success_stdout_single_url(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {
                'POLYGON_API_KEY': 'test-key', 'POLYGON_API_SECRET': 'test-secret'}), patch.object(
                polygon_upload, 'PolygonAPI'), patch.object(polygon_upload.Workflow, 'run', return_value={
                    'problem_url': 'https://polygon.codeforces.com/opaque/owner/problem'}):
            code, out, err = self.invoke(['run', '--input', str(self.input_path),
                '--state', str(Path(d) / 'state.json'), '--url-only'])
            self.assertEqual(code, 0, err)
            self.assertEqual(out, 'https://polygon.codeforces.com/opaque/owner/problem\n')

    def test_secret_redacted_in_error(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {
                'POLYGON_API_KEY': 'test-key', 'POLYGON_API_SECRET': 'test-secret'}), patch.object(
                polygon_upload, 'PolygonAPI', side_effect=ValueError('test-key and test-secret')):
            code, out, err = self.invoke(['run', '--input', str(self.input_path),
                                        '--state', str(Path(d) / 'state.json')])
            self.assertEqual(code, 1)
            self.assertNotIn('test-secret', err)
            self.assertNotIn('test-key', err)
            self.assertEqual(out, '')


if __name__ == '__main__':
    unittest.main()
