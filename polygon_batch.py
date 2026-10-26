#!/usr/bin/env python3
"""Upload problem/problem1..problem10 concurrently and collect Polygon links."""
from __future__ import annotations

import argparse
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
from threading import Event, Lock
import sys
import time

from gemini_tool.control import (StopRequested, cancellation_scope, check_stop,
                                 exclusive_lock, sleep)
from polygon_tool.api import PolygonAPI
from polygon_tool.credentials import load_credentials
from polygon_tool.image_refs import has_image_reference
from polygon_tool.input import parse_problem
from polygon_tool.problem_url import resolve_problem_url, validate_problem_url
from polygon_tool.workflow import Workflow, atomic_json, digest, state_lock
from polygon_upload import indices, nonnegative_int, positive, validate_options

ROOT = Path(__file__).resolve().parent
COUNT = 10
DEFAULT_STATE = ROOT / '.pipeline-state' / 'polygon'
_SERVER_OPTIONS = ('timeLimit', 'memoryLimit', 'inputFile', 'outputFile',
                   'source_type', 'sample_indices')


class BatchError(RuntimeError):
    """The batch has not completed all ten problems; its checkpoints are intact."""


class _RequestGate:
    """Rate limit the entire account, including every retried HTTP request."""
    def __init__(self, interval: float):
        self.interval = interval
        self.lock = Lock()
        self.last = None

    def wait(self):
        with self.lock:
            check_stop()
            if self.last is not None:
                sleep(max(0, self.interval - (time.monotonic() - self.last)))
            self.last = time.monotonic()


class _BatchAPI(PolygonAPI):
    def __init__(self, *args, gate: _RequestGate, **kwargs):
        super().__init__(*args, **kwargs)
        self.gate = gate

    def _throttle(self):
        self.gate.wait()


def discover_problems(directory: Path) -> list[Path]:
    """The numeric suffix is the problem order, including problem10 last."""
    return [Path(directory) / f'problem{number}' for number in range(1, COUNT + 1)]


def _options(overrides: dict | None = None) -> dict:
    value = {'timeLimit': None, 'memoryLimit': None, 'inputFile': None,
             'outputFile': None, 'source_type': 'cpp.g++17', 'sample_indices': None,
             'request_timeout': 60.0, 'retries': 3, 'request_interval': 1.0,
             'poll_interval': 5.0, 'poll_timeout': 900.0, 'browser_timeout': 300.0,
             'browser': False, 'browser_profile': str(ROOT / '.polygon-browser')}
    if overrides:
        unknown = set(overrides) - set(value)
        if unknown:
            raise ValueError('Tùy chọn Polygon không nhận diện: ' + ', '.join(sorted(unknown)))
        value.update(overrides)
    validate_options(value)
    for name in ('request_timeout', 'request_interval', 'poll_interval',
                 'poll_timeout', 'browser_timeout'):
        number = value[name]
        if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number) or number <= 0:
            raise ValueError(f'{name} phải là số dương hữu hạn.')
    if isinstance(value['retries'], bool) or not isinstance(value['retries'], int) or value['retries'] < 0:
        raise ValueError('retries phải là số nguyên không âm.')
    samples = value['sample_indices']
    if samples is not None and (not isinstance(samples, list) or not samples or
            any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in samples) or
            len(set(samples)) != len(samples)):
        raise ValueError('sample_indices phải gồm các số nguyên dương không trùng.')
    value['browser_profile'] = str(Path(value['browser_profile']).resolve())
    return value


def preflight(problem_dirs: list[Path]) -> list[dict]:
    if len(problem_dirs) != COUNT:
        raise ValueError(f'Cần đúng {COUNT} thư mục bài; đã nhận {len(problem_dirs)}.')
    paths = [Path(path).resolve() for path in problem_dirs]
    if len(set(paths)) != COUNT:
        raise ValueError('Các thư mục bài không được trùng nhau.')
    entries = []
    for number, path in enumerate(paths, 1):
        if not path.is_dir():
            raise ValueError(f'Bài {number}: thiếu thư mục {path}.')
        try:
            parts = parse_problem(path)
        except (ValueError, OSError) as exc:
            raise ValueError(f'Bài {number} ({path.name}): {exc}') from exc
        entries.append({'number': number, 'path': str(path),
                        'name': parts['name problem'], 'digest': digest(parts), 'parts': parts})
    names = [entry['name'] for entry in entries]
    if len(set(names)) != COUNT:
        raise ValueError('Mười bài phải có name problem khác nhau để không tạo trùng bài Polygon.')
    return entries


def _validate_paths(entries: list[dict], state_dir: Path, output_dir: Path, report: Path) -> None:
    """Never let output settings overwrite an input or another output kind."""
    def overlaps(first: Path, second: Path) -> bool:
        return first == second or first in second.parents or second in first.parents

    inputs = [Path(entry['path']) for entry in entries]
    for path in (state_dir, output_dir):
        if any(overlaps(path, source) for source in inputs):
            raise ValueError('Thư mục checkpoint/kết quả không được trùng hoặc lồng với đầu vào.')
        if path.exists() and not path.is_dir():
            raise ValueError(f'Đầu ra phải là thư mục: {path}.')
        if any(parent.exists() and not parent.is_dir() for parent in path.parents):
            raise ValueError(f'Đường dẫn đầu ra đi qua một file: {path}.')
    if overlaps(state_dir, output_dir):
        raise ValueError('Checkpoint và kết quả cần hai thư mục riêng, không lồng nhau.')
    if any(overlaps(report, directory) for directory in (*inputs, state_dir, output_dir)):
        raise ValueError('report.txt phải nằm ngoài thư mục đầu vào, checkpoint và kết quả từng bài.')
    if report == ROOT / '.env' or report.suffix.lower() != '.txt':
        raise ValueError('Báo cáo phải là một file .txt riêng.')
    if report.exists() and not report.is_file():
        raise ValueError('Đường dẫn report.txt đang là thư mục.')
    if any(parent.exists() and not parent.is_dir() for parent in report.parents):
        raise ValueError('Thư mục chứa report.txt đi qua một file.')
    for number in range(1, COUNT + 1):
        destination = output_dir / f'problem{number}'
        if destination.exists() and not destination.is_dir():
            raise ValueError(f'Đầu ra bài {number} phải là thư mục: {destination}.')


def _validate_saved_outcomes(manifest: dict) -> list[dict]:
    outcomes = manifest.get('outcomes')
    if not isinstance(outcomes, list) or len(outcomes) != COUNT:
        raise BatchError('Checkpoint lô thiếu trạng thái của đủ 10 bài; không tự tạo lại bài.')
    for outcome in outcomes:
        if (not isinstance(outcome, dict) or
                outcome.get('status') not in ('pending', 'complete', 'failed', 'stopped') or
                not isinstance(outcome.get('started'), bool) or
                (outcome['status'] == 'complete' and not outcome['started'])):
            raise BatchError('Trạng thái checkpoint lô không hợp lệ; không tự tạo lại bài.')
    return outcomes


def _reject_duplicate_results(outcomes: list[dict]) -> None:
    """Mark every colliding result as failed before publishing a success report."""
    for field in ('problem_id', 'problem_url'):
        groups = {}
        for index, outcome in enumerate(outcomes):
            result = outcome.get('result')
            if result is not None:
                groups.setdefault(result[field], []).append(index)
        for indices in groups.values():
            if len(indices) > 1:
                for index in indices:
                    outcomes[index].update(status='failed', error='ID/link Polygon trùng bài khác; kiểm tra checkpoint.')


def _write_report(path: Path, entries: list[dict], outcomes: list[dict]) -> None:
    """Atomic, ordered report; pending/failed rows are never presented as links."""
    complete = sum(item['status'] == 'complete' for item in outcomes)
    lines = [f'Polygon: {complete}/{COUNT} bài hoàn tất', '']
    for entry, outcome in zip(entries, outcomes):
        prefix = f"{entry['number']:02d}. {entry['name']}"
        if outcome['status'] == 'complete':
            lines.append(f"{prefix}: {outcome['result']['problem_url']}")
        else:
            labels = {'pending': 'CHƯA HOÀN TẤT', 'failed': 'LỖI', 'stopped': 'ĐÃ DỪNG'}
            message = outcome.get('error', '')
            # One logical row per problem, even if a remote diagnostic is multiline.
            message = ' '.join(message.splitlines())
            lines.append(f"{prefix}: {labels[outcome['status']]}" + (f' — {message}' if message else ''))
    image_warnings = [f"problem{entry['number']}, {entry['name']}, thiếu ảnh" for entry in entries
                      if has_image_reference(entry['parts'])]
    if image_warnings:
        lines.extend(['', 'Cần bổ sung ảnh thủ công trên Polygon:', *image_warnings])
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def upload_batch(problem_dirs: list[Path], *, state_dir: Path = DEFAULT_STATE,
                 output_dir: Path = ROOT / 'polygon_results',
                 report_path: Path = ROOT / 'report.txt', options: dict | None = None,
                 workers: int = COUNT, resume: bool = False, dry_run: bool = False) -> list[dict]:
    """Preflight ten inputs, run isolated workflows, and return results in input order.

    Fresh runs never adopt an existing checkpoint. Resume uses the exact saved
    input order and digests. A regular item failure does not interrupt other jobs;
    Stop/Ctrl+C cancels outstanding work cooperatively and preserves every state.
    The calling pipeline owns its lifecycle lock; standalone CLI acquires it below.
    """
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= COUNT:
        raise ValueError('workers phải nằm trong 1..10.')
    entries = preflight(problem_dirs)
    state_dir, output_dir, report_path = (Path(path).resolve() for path in (state_dir, output_dir, report_path))
    _validate_paths(entries, state_dir, output_dir, report_path)
    manifest_path = state_dir / 'batch.json'
    supplied = dict(options or {})
    current_options = _options(supplied)
    if dry_run:
        return [{'number': entry['number'], 'name': entry['name'], 'valid': True} for entry in entries]

    with state_lock(manifest_path):
        input_manifest = [{key: value for key, value in entry.items() if key != 'parts'} for entry in entries]
        if resume:
            if not manifest_path.is_file():
                raise BatchError(f'Không có checkpoint lô: {manifest_path}.')
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if not isinstance(manifest, dict) or manifest.get('version') != 1 or manifest.get('inputs') != input_manifest:
                raise BatchError('Đầu vào hoặc thứ tự bài khác checkpoint của lô. Không tiếp tục ghi lên Polygon.')
            if manifest.get('output_dir') != str(output_dir) or manifest.get('report_path') != str(report_path):
                raise BatchError('Đường dẫn kết quả/report phải khớp checkpoint khi resume.')
            if not isinstance(manifest.get('options'), dict):
                raise BatchError('Checkpoint lô thiếu tùy chọn chạy hợp lệ.')
            saved_options = _options(manifest['options'])
            for name in _SERVER_OPTIONS:
                if name in supplied and supplied[name] != saved_options[name]:
                    raise BatchError(f'Không đổi {name} trong lô đang tiếp tục.')
            saved_options.update(supplied)
            current_options = _options(saved_options)
            # A started job losing its checkpoint must never silently create anew.
            saved_outcomes = _validate_saved_outcomes(manifest)
            for entry, outcome in zip(entries, saved_outcomes):
                if outcome.get('started') and not (state_dir / f"{entry['number']:02d}.json").is_file():
                    raise BatchError(f"Bài {entry['number']}: mất checkpoint; không tự tạo bài thay thế.")
        else:
            if manifest_path.exists() or any(state_dir.glob('[0-9][0-9].json')):
                raise BatchError('Checkpoint lô đã tồn tại. Dùng resume hoặc Start để bắt đầu lượt mới.')
            manifest = {'version': 1, 'inputs': input_manifest,
                        'output_dir': str(output_dir), 'report_path': str(report_path)}

        # Credentials are loaded only after all ten local inputs and resume checks pass.
        key, secret = load_credentials(ROOT / '.env')
        outcomes = [{'status': 'pending', 'started': (state_dir / f"{entry['number']:02d}.json").is_file()}
                    for entry in entries]
        manifest.update(options=current_options, outcomes=outcomes, completed=False)
        atomic_json(manifest_path, manifest)
        _write_report(report_path, entries, outcomes)
        gate, cancellation, log_lock = _RequestGate(current_options['request_interval']), Event(), Lock()
        browser_lock = Lock()

        def log(number: int, message: str):
            with log_lock:
                print(f'[Polygon {number:02d}/10] {message}', file=sys.stderr, flush=True)

        def resolve_url(*args, **kwargs):
            # Browser fallbacks share a profile and must not open it concurrently.
            if kwargs.get('browser'):
                with browser_lock:
                    check_stop()
                    return resolve_problem_url(*args, **kwargs)
            return resolve_problem_url(*args, **kwargs)

        def upload(entry: dict) -> dict:
            with cancellation_scope(cancellation):
                check_stop()
                number = entry['number']
                path = state_dir / f'{number:02d}.json'
                api = _BatchAPI(key, secret, timeout=current_options['request_timeout'],
                                retries=current_options['retries'], interval=0, gate=gate)
                item_options = {**current_options, 'input_path': entry['path'],
                                'output_dir': str(output_dir / f'problem{number}')}
                try:
                    with state_lock(path):
                        if path.exists():
                            saved = json.loads(path.read_text(encoding='utf-8'))
                            if saved.get('version') != 1 or saved.get('input_digest') != entry['digest']:
                                raise BatchError('Checkpoint bài không khớp nội dung đầu vào.')
                            for name in _SERVER_OPTIONS:
                                if saved.get('options', {}).get(name) != item_options.get(name):
                                    raise BatchError(f'Checkpoint bài khác tùy chọn {name}.')
                        workflow = Workflow(api, path, entry['parts'], item_options,
                                            log=lambda message: log(number, message), sleep=sleep)
                        if workflow.state:
                            workflow.state['options'] = item_options
                            workflow.save()
                        result = workflow.run(resolve_url)
                        if (result.get('package_state') != 'READY' or result.get('name') != entry['name'] or
                                type(result.get('problem_id')) is not int or result['problem_id'] < 1 or
                                result.get('problem_id') != workflow.state.get('problem_id')):
                            raise BatchError('Kết quả Polygon chưa xác nhận đúng bài/package READY.')
                        validate_problem_url(result.get('problem_url'),
                                             {'owner': workflow.state.get('owner'), 'name': entry['name']})
                        log(number, 'Hoàn tất: ' + result['problem_url'])
                        return result
                except Exception as exc:
                    raise BatchError(api.redact(exc)) from None

        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='polygon')
        futures = {}
        interrupted = False
        try:
            # Persist dispatch BEFORE a worker can reach the API. If killed
            # before recording its result, a missing item checkpoint blocks
            # resume conservatively. A caught pre-create failure can explicitly
            # record started=False because no remote mutation was attempted.
            for entry in entries:
                check_stop()
                outcomes[entry['number'] - 1]['started'] = True
                atomic_json(manifest_path, manifest)
                future = executor.submit(upload, entry)
                futures[future] = entry['number'] - 1
            for future in as_completed(futures):
                index = futures[future]
                try:
                    result = future.result()
                    outcomes[index] = {'status': 'complete', 'result': result, 'started': True}
                except (StopRequested, KeyboardInterrupt):
                    interrupted = True
                    cancellation.set()
                    outcomes[index] = {'status': 'stopped', 'started': (state_dir / f'{index + 1:02d}.json').exists()}
                except Exception as exc:
                    outcomes[index] = {'status': 'failed', 'error': str(exc),
                                       'started': (state_dir / f'{index + 1:02d}.json').exists()}
                    log(index + 1, 'Lỗi: ' + str(exc))
                _reject_duplicate_results(outcomes)
                atomic_json(manifest_path, manifest)
                _write_report(report_path, entries, outcomes)
        except (StopRequested, KeyboardInterrupt):
            interrupted = True
            cancellation.set()
        finally:
            if interrupted:
                cancellation.set()
            executor.shutdown(wait=True, cancel_futures=interrupted)
            # Collect jobs that finished while main was interrupted, including
            # successes whose link has not yet reached the report.
            for future, index in futures.items():
                if outcomes[index]['status'] != 'pending':
                    continue
                try:
                    outcomes[index] = {'status': 'complete', 'result': future.result(), 'started': True}
                except (StopRequested, KeyboardInterrupt, CancelledError):
                    outcomes[index] = {'status': 'stopped', 'started': (state_dir / f'{index + 1:02d}.json').exists()}
                except Exception as exc:
                    outcomes[index] = {'status': 'failed', 'error': str(exc),
                                       'started': (state_dir / f'{index + 1:02d}.json').exists()}
            _reject_duplicate_results(outcomes)
            manifest['completed'] = all(item['status'] == 'complete' for item in outcomes)
            atomic_json(manifest_path, manifest)
            _write_report(report_path, entries, outcomes)
        if interrupted:
            raise StopRequested('Đã dừng lô Polygon; checkpoint và report đã được lưu.')
        if not manifest['completed']:
            complete = sum(item['status'] == 'complete' for item in outcomes)
            raise BatchError(f'Hoàn tất {complete}/10 bài. Xem {report_path}; dùng polygon_batch.py resume để tiếp tục.')
        results = [item['result'] for item in outcomes]
        return results


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('command', choices=('run', 'resume'))
    cli.add_argument('--input', type=Path, default=ROOT / 'problem')
    cli.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    cli.add_argument('--output-dir', type=Path, default=ROOT / 'polygon_results')
    cli.add_argument('--report', type=Path, default=ROOT / 'report.txt')
    cli.add_argument('--workers', type=int, choices=range(1, 11), default=COUNT)
    cli.add_argument('--dry-run', action='store_true')
    cli.add_argument('--time-limit', type=int)
    cli.add_argument('--memory-limit', type=int)
    cli.add_argument('--input-file')
    cli.add_argument('--output-file')
    cli.add_argument('--source-type')
    cli.add_argument('--sample-indices', type=indices)
    cli.add_argument('--request-timeout', type=positive)
    cli.add_argument('--retries', type=nonnegative_int)
    cli.add_argument('--request-interval', type=positive)
    cli.add_argument('--poll-interval', type=positive)
    cli.add_argument('--poll-timeout', type=positive)
    cli.add_argument('--browser', action='store_true', default=None)
    cli.add_argument('--browser-profile', type=Path)
    cli.add_argument('--browser-timeout', type=positive)
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    options = {key: value for key, value in vars(args).items() if key in _options() and value is not None}
    for source, target in (('time_limit', 'timeLimit'), ('memory_limit', 'memoryLimit'),
                           ('input_file', 'inputFile'), ('output_file', 'outputFile')):
        if getattr(args, source) is not None:
            options[target] = getattr(args, source)
    try:
        with exclusive_lock(ROOT / '.pipeline-run.lock'):
            # Stop leaves a cancellation marker. An explicit new/resumed CLI
            # invocation clears it only after excluding an active Gemini run
            # or concurrent reset; it never clears another process's request.
            if not args.dry_run:
                with exclusive_lock(ROOT / '.gemini-reset.lock'):
                    with exclusive_lock(ROOT / '.gemini-upload.lock'):
                        (ROOT / '.gemini-stop-request').unlink(missing_ok=True)
            results = upload_batch(discover_problems(args.input), state_dir=args.state_dir,
                                   output_dir=args.output_dir, report_path=args.report,
                                   options=options, workers=args.workers,
                                   resume=args.command == 'resume', dry_run=args.dry_run)
        print(f"Đã kiểm tra {len(results)} bài." if args.dry_run else f'Hoàn tất 10 bài. Link: {args.report}')
        return 0
    except (StopRequested, KeyboardInterrupt):
        print('Đã dừng. Dùng polygon_batch.py resume để tiếp tục cùng các bài.', file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Chưa hoàn tất: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
