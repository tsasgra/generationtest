"""Offline integration checks; remote Gemini/Polygon boundaries are simulated."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import pipeline
from gemini_tool import control
from gemini_tool.images import archive_uploaded
from gemini_tool.parts import parts_from_events, write_parts
from gemini_tool.stop import is_tool_process, is_uploader
from polygon_tool import batch
from polygon_tool.input import PARTS, discover_problems, parse_problem
from polygon_tool.workflow import atomic_json, digest


def response(number):
    parts = {part: f'Content for {part}\n' for part in PARTS}
    parts.update({'name problem': f'task-{number}', 'name': f'Bài {number}', 'note': ''})
    return [event for index, part in enumerate(PARTS, 1)
            for event in ({'part': index}, {'code': parts[part]})]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.held = ExitStack()
        self.addCleanup(self.held.close)
        self.root = Path(self.held.enter_context(tempfile.TemporaryDirectory()))
        self.events = []
        self.failures = set()
        self.held.enter_context(redirect_stdout(io.StringIO()))
        self.held.enter_context(redirect_stderr(io.StringIO()))
        self.held.enter_context(patch.object(control, 'STOP_FILE', self.root / '.gemini-stop-request'))
        self.held.enter_context(patch.object(batch, 'ROOT', self.root))
        self.held.enter_context(patch.dict('os.environ', {}, clear=True))
        (self.root / '.env').write_text('POLYGON_API_KEY=fixture-key\nPOLYGON_API_SECRET=fixture-secret\n')
        test = self

        class RemoteWorkflow:
            """Only the remote workflow is substituted; state/report logic is real."""
            def __init__(self, api, path, parts, options, **kwargs):
                self.path, self.parts, self.options = path, parts, options
                self.state = json.loads(path.read_text()) if path.exists() else {}

            def save(self):
                atomic_json(self.path, self.state)

            def run(self, resolver):
                number = int(self.parts['name problem'].split('-')[-1])
                if not self.state:
                    test.events.append(('create', number))
                    self.state = {'version': 1, 'input_digest': digest(self.parts),
                                  'options': self.options, 'problem_id': number, 'owner': 'tester'}
                    self.save()
                if number in test.failures:
                    raise RuntimeError('simulated package failure')
                result = {'problem_id': number, 'name': self.parts['name problem'],
                          'package_state': 'READY', 'package_id': 100 + number,
                          'problem_url': f'https://polygon.codeforces.com/fixture/tester/task-{number}'}
                self.state.update(completed=True, result=result)
                self.save()
                test.events.append(('complete', number))
                return result

        self.held.enter_context(patch.object(batch, 'Workflow', RemoteWorkflow))
        self.remote = self.held.enter_context(patch.object(pipeline, 'upload_tasks', side_effect=self.gemini))

    def images(self, *numbers, parentheses=False):
        for number in numbers:
            folder = self.root / 'img' / (f'img({number})' if parentheses else f'img{number}')
            folder.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (8, 8), 'white').save(folder / 'page.png')

    def problem(self, number):
        folder = self.root / 'problem' / f'problem{number}'
        write_parts(parts_from_events(response(number)), folder)
        return folder

    def gemini(self, tasks, **options):
        for task in tasks:
            number = int(task.label.removeprefix('problem'))
            # Real response parsing, file writes and image archiving.
            write_parts(parts_from_events(response(number)), task.output)
            self.assertEqual(archive_uploaded(task.images, task.output / 'img'), [])
            self.events.append(('export', number))

    def run_pipeline(self, command='run'):
        args = pipeline.parser().parse_args([command, '--profile', str(self.root / '.browser')])
        return pipeline.execute(args, root=self.root)

    def upload(self, numbers, **kwargs):
        return batch.upload_batch([self.root / 'problem' / f'problem{number}' for number in numbers],
                                  state_dir=self.root / '.pipeline-state' / 'polygon',
                                  output_dir=self.root / 'polygon_results', report_path=self.root / 'report.txt',
                                  **kwargs)

    def test_full_pipeline_orders_stages_and_preserves_sparse_numbers(self):
        self.images(2, 10, parentheses=True)
        self.assertEqual(self.run_pipeline(), 0)
        self.assertEqual(self.events[:2], [('export', 2), ('export', 10)])
        self.assertEqual({n for kind, n in self.events if kind == 'create'}, {2, 10})
        for n in (2, 10):
            self.assertEqual(parse_problem(self.root / 'problem' / f'problem{n}')['name problem'], f'task-{n}')
            self.assertTrue((self.root / 'problem' / f'problem{n}' / 'img' / 'page.png').is_file())
            self.assertFalse((self.root / 'img' / f'img({n})' / 'page.png').exists())
            self.assertTrue((self.root / '.pipeline-state' / 'polygon' / f'{n:02d}.json').is_file())
        report = (self.root / 'report.txt').read_text()
        self.assertIn('2/2', report)
        self.assertLess(report.index('02. task-2'), report.index('10. task-10'))
        self.assertFalse(list((self.root / '.gemini-runtime').glob('upload-*')))

    def test_all_ten_problems(self):
        self.images(*range(1, 11))
        self.assertEqual(self.run_pipeline(), 0)
        self.assertIn('10/10', (self.root / 'report.txt').read_text())

    def test_single_problem(self):
        self.images(7)
        self.assertEqual(self.run_pipeline(), 0)
        self.assertIn('1/1', (self.root / 'report.txt').read_text())

    def test_incomplete_gemini_output_never_reaches_polygon(self):
        self.images(1, 2)
        def incomplete(tasks, **kwargs):
            self.problem(1)
            self.problem(2)
            (self.root / 'problem/problem2/solution.txt').unlink()
        self.remote.side_effect = incomplete
        with self.assertRaisesRegex(ValueError, 'solution.txt'):
            self.run_pipeline()
        self.assertEqual(self.events, [])
        self.assertFalse((self.root / '.pipeline-state/polygon/batch.json').exists())

    def test_gemini_error_never_reaches_polygon(self):
        self.images(1)
        self.remote.side_effect = RuntimeError('Gemini timeout')
        with self.assertRaisesRegex(RuntimeError, 'Gemini timeout'):
            self.run_pipeline()
        self.assertEqual(self.events, [])
        self.assertTrue((self.root / 'img/img1/page.png').exists())

    def test_duplicate_slugs_fail_before_any_remote_creation(self):
        self.problem(1)
        second = self.problem(2)
        (second / 'name problem.txt').write_text('task-1')
        with self.assertRaisesRegex(ValueError, 'trùng'):
            self.upload([1, 2])
        self.assertEqual(self.events, [])

    def test_missing_credentials_keep_old_outputs(self):
        self.images(1)
        self.problem(1)
        (self.root / '.env').unlink()
        with self.assertRaises(ValueError):
            self.run_pipeline()
        self.assertEqual(parse_problem(self.root / 'problem/problem1')['name problem'], 'task-1')
        self.remote.assert_not_called()

    def test_empty_images_keep_old_outputs(self):
        old = self.problem(1)
        with self.assertRaisesRegex(ValueError, 'Chưa có ảnh'):
            self.run_pipeline()
        self.assertTrue((old / 'solution.txt').exists())
        self.remote.assert_not_called()

    def test_corrupt_image_keeps_old_outputs(self):
        self.images(1)
        old = self.problem(1)
        (self.root / 'img/img1/broken.png').write_bytes(b'not an image')
        with self.assertRaises(ValueError):
            self.run_pipeline()
        self.assertTrue((old / 'solution.txt').exists())
        self.remote.assert_not_called()

    def test_multiframe_input_rejected_without_reset(self):
        self.images(1)
        old = self.problem(1)
        Image.new('RGB', (8, 8), 'white').save(self.root / 'img/img1/multi.gif', save_all=True,
                                            append_images=[Image.new('RGB', (8, 8), 'black')])
        with self.assertRaisesRegex(ValueError, 'nhiều trang'):
            self.run_pipeline()
        self.assertTrue((old / 'solution.txt').exists())

    def test_check_is_offline_and_keeps_previous_results(self):
        self.images(1)
        old = self.problem(1)
        (self.root / '.env').unlink()
        self.assertEqual(self.run_pipeline('check'), 0)
        self.assertTrue((old / 'solution.txt').exists())
        self.remote.assert_not_called()
        self.assertEqual(self.events, [])

    def test_start_clears_stale_stop_after_taking_locks(self):
        self.images(1)
        control.STOP_FILE.touch()
        self.assertEqual(self.run_pipeline(), 0)
        self.assertFalse(control.STOP_FILE.exists())

    def test_partial_batch_failure_and_resume_reuse_ids(self):
        for n in (2, 10):
            self.problem(n)
        self.failures.add(10)
        with self.assertRaises(batch.BatchError):
            self.upload([10, 2])
        state = json.loads((self.root / '.pipeline-state/polygon/batch.json').read_text())
        self.assertEqual([x['number'] for x in state['inputs']], [2, 10])
        self.assertEqual([x['status'] for x in state['outcomes']], ['complete', 'failed'])
        self.assertTrue(all(x['started'] for x in state['outcomes']))
        self.failures.clear()
        results = self.upload([2, 10], resume=True)
        self.assertEqual([x['problem_id'] for x in results], [2, 10])
        self.assertEqual(sorted(n for kind, n in self.events if kind == 'create'), [2, 10])

    def test_resume_refuses_missing_checkpoint(self):
        self.problem(10)
        self.upload([10])
        (self.root / '.pipeline-state/polygon/10.json').unlink()
        with self.assertRaisesRegex(batch.BatchError, 'mất checkpoint'):
            self.upload([10], resume=True)

    def test_resume_refuses_changed_input(self):
        folder = self.problem(2)
        self.upload([2])
        (folder / 'input.txt').write_text('changed')
        with self.assertRaisesRegex(batch.BatchError, 'Đầu vào'):
            self.upload([2], resume=True)

    def test_discovery_skips_empty_slots_but_rejects_partial_set(self):
        pipeline.initialize(self.root)
        self.problem(10)
        self.assertEqual(discover_problems(self.root / 'problem'), [self.root / 'problem/problem10'])
        (self.root / 'problem/problem2/input.txt').write_text('partial')
        with self.assertRaises(ValueError):
            batch.preflight(discover_problems(self.root / 'problem'))

    def test_duplicate_image_alias_is_rejected(self):
        self.images(1)
        self.images(1, parentheses=True)
        with self.assertRaisesRegex(ValueError, 'Trùng thư mục'):
            self.run_pipeline()
        self.remote.assert_not_called()

    def test_part_parser_rejects_missing_duplicate_and_empty_parts(self):
        for events in (response(1)[:-2], response(1) + [{'part': 1}],
                       response(1)[:-1] + [{'code': ''}]):
            with self.subTest(events=events[-1]):
                with self.assertRaises(ValueError):
                    parts_from_events(events)

    def test_stop_recognizes_new_module_commands(self):
        for module in ('gemini_tool.cli', 'polygon_tool.cli', 'polygon_tool.batch'):
            process = {'Name': 'python.exe', 'CommandLine': f'python.exe -u -m {module}'}
            self.assertTrue(is_tool_process(process, self.root))
            self.assertEqual(is_uploader(process), module == 'gemini_tool.cli')
        self.assertFalse(is_tool_process({'Name': 'python.exe',
                                         'CommandLine': 'python.exe -c "print(1)" pipeline.py'}, self.root))

    def test_single_recovery_options_survive_batch_resume(self):
        self.problem(1)
        self.upload([1])
        path = self.root / '.pipeline-state/polygon/01.json'
        state = json.loads(path.read_text())
        state['options']['package_id'] = 101
        atomic_json(path, state)
        self.upload([1], resume=True)
        self.assertEqual(json.loads(path.read_text())['options']['package_id'], 101)

    def test_unified_cli_dispatches_without_extra_installation(self):
        with patch.object(batch, 'main', return_value=0) as main, \
                patch.object(pipeline, '_python_with_dependencies') as setup:
            self.assertEqual(pipeline.main(['resume', '--workers', '2']), 0)
            main.assert_called_once_with(['resume', '--workers', '2'])
            setup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
