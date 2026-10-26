"""Offline integration checks; remote Gemini/Polygon boundaries are simulated."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import pipeline
import pipeline_reset
from gemini_tool import control
from gemini_tool.images import archive_uploaded, delete_uploaded, prepare_images
from gemini_tool.parts import parts_from_events, write_parts
from gemini_tool.stop import is_tool_process, is_uploader
from polygon_tool import batch, cli
from polygon_tool.input import PARTS, discover_problems, init_batch, parse_problem
from polygon_tool.stop import is_uploader as is_polygon_uploader
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
                self.step = 'test-remote'
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
        self.assertEqual(self.events, [('export', 2), ('create', 2), ('complete', 2),
                                       ('export', 10), ('create', 10), ('complete', 10)])
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
        self.assertEqual(self.events, [(event, number) for number in range(1, 11)
                                       for event in ('export', 'create', 'complete')])
        self.assertIn('10/10', (self.root / 'report.txt').read_text())

    def test_pipeline_polygon_failure_blocks_next_gemini_and_resume_finishes_queue(self):
        self.images(1, 2, 10)
        self.failures.add(2)
        with self.assertRaises(batch.BatchError):
            self.run_pipeline()
        self.assertEqual(self.events, [('export', 1), ('create', 1), ('complete', 1),
                                       ('export', 2), ('create', 2)])
        self.assertTrue((self.root / 'img/img10/page.png').exists())
        manifest = json.loads((self.root / '.pipeline-state/polygon/batch.json').read_text())
        self.assertEqual([row['status'] for row in manifest['outcomes']], ['complete', 'failed', 'pending'])
        self.assertIsNone(manifest['inputs'][2]['digest'])
        self.assertIn('1/3', (self.root / 'report.txt').read_text())
        self.failures.clear()
        self.assertEqual(self.run_pipeline('resume'), 0)
        self.assertEqual(self.events, [('export', 1), ('create', 1), ('complete', 1),
                                       ('export', 2), ('create', 2), ('complete', 2),
                                       ('export', 10), ('create', 10), ('complete', 10)])
        self.assertIn('3/3', (self.root / 'report.txt').read_text())
        self.assertEqual(self.remote.call_count, 3)

    def test_pipeline_gemini_failure_resumes_without_repeating_completed_problem(self):
        self.images(1, 2, 3)
        def fail_second(tasks, **options):
            if tasks[0].label == 'problem2':
                raise RuntimeError('Gemini failed')
            self.gemini(tasks, **options)
        self.remote.side_effect = fail_second
        with self.assertRaises(batch.BatchError):
            self.run_pipeline()
        self.assertEqual(self.events, [('export', 1), ('create', 1), ('complete', 1)])
        self.remote.side_effect = self.gemini
        self.assertEqual(self.run_pipeline('resume'), 0)
        self.assertEqual(self.events, [(event, number) for number in (1, 2, 3)
                                       for event in ('export', 'create', 'complete')])

    def test_resume_reuses_response_exported_just_before_stop(self):
        self.images(1, 2)
        def export_then_stop(tasks, **options):
            self.gemini(tasks, **options)
            raise control.StopRequested('after export')
        self.remote.side_effect = export_then_stop
        with self.assertRaises(control.StopRequested):
            self.run_pipeline()
        self.assertEqual(self.events, [('export', 1)])
        self.remote.side_effect = self.gemini
        self.assertEqual(self.run_pipeline('resume'), 0)
        self.assertEqual(self.events, [(event, number) for number in (1, 2)
                                       for event in ('export', 'create', 'complete')])
        self.assertEqual(self.remote.call_count, 2)

    def test_duplicate_later_slug_stops_before_its_polygon_upload(self):
        self.images(1, 2)
        def duplicate(tasks, **options):
            self.gemini(tasks, **options)
            if tasks[0].label == 'problem2':
                (tasks[0].output / 'name problem.txt').write_text('task-1')
        self.remote.side_effect = duplicate
        with self.assertRaisesRegex(batch.BatchError, 'trùng'):
            self.run_pipeline()
        self.assertEqual([number for event, number in self.events if event == 'create'], [1])

    def test_standalone_polygon_stops_at_first_failure(self):
        self.problem(2)
        self.problem(10)
        self.failures.add(2)
        with self.assertRaises(batch.BatchError):
            self.upload([2, 10])
        self.assertEqual(self.events, [('create', 2)])
        manifest = json.loads((self.root / '.pipeline-state/polygon/batch.json').read_text())
        self.assertEqual(manifest['outcomes'][1], {'status': 'pending', 'started': False})

    def test_resume_loads_saved_pipeline_profile_and_timeouts(self):
        profile = self.root / '.saved-profile'
        with patch.object(pipeline, 'saved_pipeline_options', return_value={
                'profile': str(profile), 'response_timeout': 1234, 'workers': 1}), \
                patch.object(pipeline, 'execute', return_value=0) as execute:
            self.assertEqual(pipeline.run_pipeline(['resume']), 0)
            args = execute.call_args.args[0]
            self.assertEqual(args.profile, profile)
            self.assertEqual(args.response_timeout, 1234)

    def test_parallel_cli_options_are_rejected(self):
        for parser, arguments in (
                (pipeline.parser(), ['run', '--workers', '10']),
                (pipeline.parser(), ['run', '--polygon-workers', '10']),
                (batch.parser(), ['run', '--workers', '10']),
                (cli.parser(), ['run', '--input', 'problem', '--jobs', '10'])):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as error:
                parser.parse_args(arguments)
            self.assertEqual(error.exception.code, 2)

    def test_menu_start_opens_worker_and_stop_stays_available(self):
        with patch.object(sys, 'platform', 'win32'), \
                patch('builtins.input', side_effect=['1', '2', '0']), \
                patch.object(pipeline.subprocess, 'Popen') as launch, \
                patch.object(pipeline, 'main', return_value=0) as command:
            self.assertEqual(pipeline.menu(), 0)
            launch.assert_called_once_with(
                [sys.executable, '-u', str(pipeline.ROOT / 'pipeline.py'), 'menu-task', 'run'],
                cwd=pipeline.ROOT, creationflags=0x10)
            launch.return_value.wait.assert_not_called()
            command.assert_called_once_with(['stop'])

    def test_menu_forwards_cli_arguments_unchanged(self):
        with patch.object(pipeline, 'main', return_value=7) as command:
            self.assertEqual(pipeline.menu(['gemini', '--input', 'a folder']), 7)
            command.assert_called_once_with(['gemini', '--input', 'a folder'])

    def test_stop_preserves_menu_but_recognizes_its_workers(self):
        for command in ('python.exe pipeline.py menu', 'python.exe -m pipeline menu'):
            self.assertFalse(is_tool_process({'Name': 'python.exe', 'CommandLine': command}, self.root))
        for command in ('python.exe pipeline.py menu-task run',
                        'python.exe pipeline.py menu run',
                        'python.exe -m pipeline menu run'):
            self.assertTrue(is_tool_process({'Name': 'python.exe', 'CommandLine': command}, self.root))
        self.assertTrue(is_polygon_uploader({'Name': 'python.exe',
            'CommandLine': 'python.exe pipeline.py menu-task polygon-legacy auto'}))

    def test_start_replaces_previous_worker_before_taking_its_run_lock(self):
        self.images(1)
        previous = ExitStack()
        self.addCleanup(previous.close)
        previous.enter_context(control.exclusive_lock(self.root / '.pipeline-run.lock'))
        self.problem(1)
        (self.root / 'report.txt').write_text('old report')
        atomic_json(self.root / '.pipeline-state/old.json', {'pending': True})
        atomic_json(self.root / 'results/problem1/result.json', {'old': True})
        profile = self.root / '.browser/chrome/Default'
        profile.mkdir(parents=True)
        (profile / 'Cookies').write_bytes(b'saved-login')
        with patch.object(pipeline_reset, 'stop_previous_run', side_effect=lambda *args: previous.close()) as stop:
            self.assertEqual(self.run_pipeline(), 0)
            stop.assert_called_once()
        self.assertFalse((self.root / '.pipeline-state/old.json').exists())
        self.assertFalse((self.root / 'results').exists())
        self.assertNotIn('old report', (self.root / 'report.txt').read_text())
        self.assertEqual((profile / 'Cookies').read_bytes(), b'saved-login')
        self.assertTrue((self.root / '.env').is_file())

    def test_windows_restart_requests_stop_and_cleans_owned_runtime(self):
        def reset(root, profiles, *, stop_processes):
            self.assertTrue((root / '.gemini-stop-request').is_file())
            self.assertTrue(stop_processes)
            self.assertEqual(profiles, [self.root / '.browser'])
        with patch.object(sys, 'platform', 'win32'), \
                patch.object(pipeline_reset, 'reset_run', side_effect=reset) as reset_run:
            pipeline_reset.stop_previous_run(self.root, self.root / '.browser')
            reset_run.assert_called_once()

    def test_failed_stop_does_not_erase_outputs_or_start_new_upload(self):
        self.images(1)
        old = self.problem(1)
        atomic_json(self.root / '.pipeline-state/old.json', {'pending': True})
        with patch.object(pipeline_reset, 'stop_previous_run', side_effect=RuntimeError('still running')):
            with self.assertRaisesRegex(RuntimeError, 'still running'):
                self.run_pipeline()
        self.assertTrue((old / 'solution.txt').is_file())
        self.assertTrue((self.root / '.pipeline-state/old.json').is_file())
        self.remote.assert_not_called()

    def test_start_stops_old_setup_before_dependency_installation(self):
        calls = []
        with patch.object(pipeline, 'ROOT', self.root), \
                patch.object(pipeline_reset, 'stop_previous_run', side_effect=lambda *args: calls.append('stop')), \
                patch.object(pipeline, '_python_with_dependencies', side_effect=lambda: calls.append('setup') or Path(sys.executable)), \
                patch.object(pipeline, 'run_pipeline', side_effect=lambda args: calls.append('run') or 0):
            self.assertEqual(pipeline.main(['run']), 0)
        self.assertEqual(calls, ['stop', 'setup', 'run'])

    def test_resume_falls_back_to_legacy_checkpoint_without_reset(self):
        (self.root / 'run_state.json').write_text('{}')
        with patch.object(pipeline, 'ROOT', self.root), \
                patch.object(cli, 'legacy_launch', return_value=0) as resume, \
                patch.object(pipeline_reset, 'stop_previous_run') as stop:
            self.assertEqual(pipeline.main(['resume']), 0)
            resume.assert_called_once_with(['resume', '--state', str(self.root / 'run_state.json')])
            stop.assert_not_called()

    def test_single_problem(self):
        self.images(7)
        self.assertEqual(self.run_pipeline(), 0)
        self.assertIn('1/1', (self.root / 'report.txt').read_text())

    def test_incomplete_gemini_output_stops_before_uploading_that_problem(self):
        self.images(1, 2)
        def incomplete(tasks, **kwargs):
            if tasks[0].label == 'problem1':
                self.gemini(tasks, **kwargs)
            else:
                self.problem(2)
                (self.root / 'problem/problem2/solution.txt').unlink()
        self.remote.side_effect = incomplete
        with self.assertRaisesRegex(batch.BatchError, 'solution.txt'):
            self.run_pipeline()
        self.assertEqual(self.events, [('export', 1), ('create', 1), ('complete', 1)])
        self.assertFalse((self.root / '.pipeline-state/polygon/02.json').exists())
        self.assertIn('1/2', (self.root / 'report.txt').read_text())

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
            self.assertEqual(pipeline.main(['resume', '--workers', '1']), 0)
            main.assert_called_once_with(['resume', '--workers', '1'])
            setup.assert_not_called()


    def test_blank_templates_are_not_uploaded(self):
        init_batch(self.root / 'problem')
        self.assertEqual(discover_problems(self.root / 'problem'), [])
        self.problem(2)
        self.problem(10)
        paths = discover_problems(self.root / 'problem')
        self.assertEqual([path.name for path in paths], ['problem2', 'problem10'])
        # A partially edited template must be reported, never silently skipped.
        (self.root / 'problem/problem3/input.txt').write_text('incomplete')
        with self.assertRaises(ValueError):
            batch.preflight(discover_problems(self.root / 'problem'))

    def test_legacy_cli_init_count_restores_all_parts(self):
        target = self.root / 'templates'
        self.assertEqual(cli.main(['init', '--output', str(target), '--count', '3']), 0)
        self.assertEqual(len(list(target.glob('problem*/*.txt'))), 30)
        self.assertEqual(cli.main(['init', '--output', str(target), '--count', '3']), 1)

    def test_legacy_single_and_batch_dry_run_remain_offline(self):
        self.problem(2)
        self.problem(10)
        with patch.object(cli, 'load_credentials') as credentials:
            for folder in (self.root / 'problem/problem2', self.root / 'problem'):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(cli.main(['run', '--input', str(folder), '--dry-run', '--jobs', '1']), 0)
                self.assertTrue(json.loads(output.getvalue())['valid'])
            credentials.assert_not_called()

    def test_legacy_batch_run_and_resume_preserve_child_checkpoints(self):
        self.problem(2)
        self.problem(10)
        state = self.root / 'run_state.json'
        arguments = ['--state', str(state), '--output-dir', str(self.root / 'legacy_results')]
        self.failures.add(10)
        with patch.object(cli, 'DEFAULT_ENV_FILE', self.root / '.env'):
            self.assertEqual(cli.main(['run', '--input', str(self.root / 'problem'), '--jobs', '1', *arguments]), 1)
            saved = json.loads(state.read_text())
            self.assertEqual(saved['kind'], 'batch')
            self.assertEqual([row['folder'] for row in saved['problems']], ['problem2', 'problem10'])
            self.assertTrue((self.root / 'run_state.problems/problem10.json').exists())
            saved['options']['jobs'] = 10  # Old checkpoints must also resume one at a time.
            atomic_json(state, saved)
            self.failures.clear()
            self.assertEqual(cli.main(['resume', *arguments]), 0)
            self.assertEqual(json.loads(state.read_text())['options']['jobs'], 1)
        self.assertEqual(sorted(n for kind, n in self.events if kind == 'create'), [2, 10])
        results = json.loads((self.root / 'legacy_results/result.json').read_text())
        self.assertEqual(results['completed'], 2)

    def test_fresh_pipeline_clears_legacy_child_progress(self):
        self.images(1)
        atomic_json(self.root / 'run_state.json', {'kind': 'batch'})
        child = self.root / 'run_state.problems/problem1.json'
        atomic_json(child, {'old': True})
        self.assertEqual(self.run_pipeline(), 0)
        self.assertFalse((self.root / 'run_state.json').exists())
        self.assertFalse(child.exists())
        # Retained lock files must not block a later standalone batch.
        folder = self.root / 'problem/problem1'
        batch.BatchWorkflow(self.root / 'run_state.json', [folder], [parse_problem(folder)],
                            {'request_interval': 1.0})

    def test_legacy_launcher_auto_resume_and_check_routes(self):
        with patch.object(cli, 'main', return_value=0) as main:
            with patch.object(Path, 'exists', return_value=False):
                self.assertEqual(cli.legacy_launch(['auto']), 0)
                main.assert_called_with(['run', '--input', 'problem', '--state', 'run_state.json'])
            with patch.object(Path, 'exists', return_value=True):
                self.assertEqual(cli.legacy_launch(['auto']), 0)
                main.assert_called_with(['resume', '--state', 'run_state.json'])
            self.assertEqual(cli.legacy_launch(['check']), 0)
            main.assert_called_with(['run', '--input', 'problem', '--dry-run'])

    def test_legacy_stop_recognizes_only_polygon_commands(self):
        for command in ('python.exe polygon_upload.py run --input problem',
                        'python.exe -m polygon_tool.cli resume',
                        'python.exe pipeline.py polygon-one run',
                        'python.exe pipeline.py polygon-legacy auto'):
            self.assertTrue(is_polygon_uploader({'Name': 'python.exe', 'CommandLine': command}))
        for command in ('python.exe pipeline.py run', 'python.exe pipeline.py polygon-legacy stop',
                        'python.exe -c "print(1)" polygon_upload.py run'):
            self.assertFalse(is_polygon_uploader({'Name': 'python.exe', 'CommandLine': command}))

    def test_legacy_delete_helper_keeps_changed_images(self):
        self.images(1)
        original = self.root / 'img/img1/page.png'
        prepared = prepare_images([original], self.root / 'prepared', 20)
        original.write_bytes(b'changed since upload')
        self.assertTrue(delete_uploaded(prepared))
        self.assertTrue(original.exists())


if __name__ == '__main__':
    unittest.main()
