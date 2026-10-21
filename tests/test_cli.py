import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import polygon_upload


ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = polygon_upload.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_offline_without_credentials_or_state(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True), patch.object(
                polygon_upload, 'PolygonAPI', side_effect=AssertionError('Network forbidden')):
            state = Path(d) / 'state.json'
            code, out, err = self.invoke(['run', '--input', str(ROOT / 'examples/a_plus_b.txt'),
                                          '--dry-run', '--state', str(state)])
            self.assertEqual(code, 0, err)
            self.assertTrue(json.loads(out)['valid'])
            self.assertFalse(state.exists())
            self.assertFalse(state.with_name('state.json.lock').exists())

    def test_init_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'problem.txt'
            self.assertEqual(self.invoke(['init', '--output', str(path)])[0], 0)
            self.assertEqual(path.read_text(encoding='utf-8').count('<<<PART:'), 10)
            original = path.read_bytes()
            self.assertEqual(self.invoke(['init', '--output', str(path)])[0], 1)
            self.assertEqual(path.read_bytes(), original)

    def test_invalid_limits_rejected_before_network(self):
        with patch.object(polygon_upload, 'PolygonAPI', side_effect=AssertionError('Network forbidden')):
            for args in (['--time-limit', '251'], ['--memory-limit', '1025'],
                         ['--input-file', 'same', '--output-file', 'SAME']):
                code, _, _ = self.invoke(['run', '--input', str(ROOT / 'examples/a_plus_b.txt'), '--dry-run', *args])
                self.assertEqual(code, 1)

    def test_url_only_failure_stdout_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            code, out, err = self.invoke(['run', '--input', str(ROOT / 'examples/a_plus_b.txt'), '--url-only'])
            self.assertEqual(code, 1)
            self.assertEqual(out, '')
            self.assertIn('POLYGON_API_KEY', err)

    def test_url_only_success_stdout_single_url(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {
                'POLYGON_API_KEY': 'test-key', 'POLYGON_API_SECRET': 'test-secret'}), patch.object(
                polygon_upload, 'PolygonAPI'), patch.object(polygon_upload.Workflow, 'run', return_value={
                    'problem_url': 'https://polygon.codeforces.com/opaque/owner/problem'}):
            code, out, err = self.invoke(['run', '--input', str(ROOT / 'examples/a_plus_b.txt'),
                '--state', str(Path(d) / 'state.json'), '--url-only'])
            self.assertEqual(code, 0, err)
            self.assertEqual(out, 'https://polygon.codeforces.com/opaque/owner/problem\n')

    def test_secret_redacted_in_error(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {
                'POLYGON_API_KEY': 'test-key', 'POLYGON_API_SECRET': 'test-secret'}), patch.object(
                polygon_upload, 'PolygonAPI', side_effect=ValueError('test-key and test-secret')):
            code, out, err = self.invoke(['run', '--input', str(ROOT / 'examples/a_plus_b.txt'),
                                        '--state', str(Path(d) / 'state.json')])
            self.assertEqual(code, 1)
            self.assertNotIn('test-secret', err)
            self.assertNotIn('test-key', err)
            self.assertEqual(out, '')


if __name__ == '__main__':
    unittest.main()
