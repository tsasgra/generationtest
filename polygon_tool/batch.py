"""Concurrent uploads with one durable checkpoint per Polygon problem."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import threading
import time

from .api import PolygonAPI
from .workflow import Workflow, WorkflowError, atomic_json, digest, state_lock


class BatchInterrupted(WorkflowError):
    pass


class RequestGate:
    """Space request starts across all workers, including retries and polling."""

    def __init__(self, interval, cancelled):
        self.interval = interval
        self.cancelled = cancelled
        self.lock = threading.Lock()
        self.last = None

    def __call__(self):
        with self.lock:
            delay = 0 if self.last is None else max(0, self.interval - (time.monotonic() - self.last))
            if self.cancelled.wait(delay):
                raise BatchInterrupted('Đã yêu cầu dừng đợt upload.')
            self.last = time.monotonic()


class BatchWorkflow:
    def __init__(self, state_path, paths, problems, options, *, resume=False,
                 sample_override=False):
        self.path = Path(state_path).resolve()
        self.options = options
        self.problems = problems
        self.step = 'batch-preflight'
        self.sample_override = sample_override
        self.cancelled = threading.Event()
        self.gate = RequestGate(options['request_interval'], self.cancelled)
        self.browser_lock = threading.Lock()
        self.log_lock = threading.Lock()
        children = self.path.with_name(self.path.stem + '.problems')
        entries = [{'folder': path.name, 'input_path': str(path),
                    'name': parts['name problem'],
                    'state_path': str(children / f'{path.name}.json')}
                   for path, parts in zip(paths, problems)]
        if resume:
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
            if (self.state.get('version') != 1 or self.state.get('kind') != 'batch'
                    or self.state.get('problems') != entries):
                raise ValueError('Danh sách/thư mục/tên bài khác checkpoint đợt upload. Giữ nguyên để resume.')
        else:
            # Never silently attach stale child checkpoints to a new run.
            if children.exists() and any(children.iterdir()):
                raise ValueError(f'Đã có checkpoint con trong {children}. Dùng resume hoặc --state mới.')
            self.state = {'version': 1, 'kind': 'batch', 'problems': entries}
        self.state['options'] = options

    def log(self, folder, message):
        with self.log_lock:
            print(f'[{folder}] {message}', file=sys.stderr)

    def sleep(self, seconds):
        if self.cancelled.wait(seconds):
            raise BatchInterrupted('Đã yêu cầu dừng đợt upload.')

    def _run_one(self, entry, parts, key, secret, url_resolver):
        folder = entry['folder']
        path = Path(entry['state_path'])
        api = PolygonAPI(key, secret, timeout=self.options['request_timeout'],
                         retries=self.options['retries'], interval=self.options['request_interval'],
                         request_gate=self.gate)
        workflow = None
        try:
            if self.cancelled.is_set():
                raise BatchInterrupted('Đã yêu cầu dừng đợt upload.')
            with state_lock(path):
                previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
                if previous and previous.get('version') != 1:
                    raise ValueError('Phiên bản checkpoint con không được hỗ trợ.')
                if previous and previous.get('input_digest') != digest(parts):
                    raise ValueError('Nội dung input khác checkpoint. Sửa riêng bài bằng resume --update-input.')
                options = dict(previous.get('options', self.options))
                # Keep per-problem recovery choices and corrected samples. Only
                # transport/browser settings are common to the resumed batch.
                for name in ('request_timeout', 'request_interval', 'retries', 'poll_interval',
                             'poll_timeout', 'browser', 'browser_profile', 'browser_timeout'):
                    options[name] = self.options[name]
                if self.sample_override:
                    samples = self.options['sample_indices']
                    if previous.get('committed') and samples != options.get('sample_indices'):
                        raise ValueError('Không đổi sample sau commit; sửa riêng bài bằng --update-input.')
                    options['sample_indices'] = samples
                options.update(input_path=entry['input_path'],
                               output_dir=str(Path(self.options['output_dir']) / 'results' / folder))
                if previous.get('completed'):
                    result = previous['result']
                    self._write_problem_result(options, result)
                    self.log(folder, 'Đã hoàn tất từ trước; giữ nguyên bài và package.')
                else:
                    self.log(folder, 'Tiếp tục checkpoint.' if previous else 'Bắt đầu tải bài.')
                    workflow = Workflow(api, path, parts, options,
                                        log=lambda message: self.log(folder, message), sleep=self.sleep)
                    if workflow.state:
                        workflow.state['options'] = options
                        workflow.save()

                    def resolve(*args, **kwargs):
                        # A persistent browser profile can only be opened once.
                        # API-only URL extraction needs no serialization.
                        if not kwargs.get('browser'):
                            return url_resolver(*args, **kwargs)
                        with self.browser_lock:
                            if self.cancelled.is_set():
                                raise BatchInterrupted('Đã yêu cầu dừng đợt upload.')
                            return url_resolver(*args, **kwargs)

                    result = workflow.run(resolve)
                    self.log(folder, f'Hoàn tất: {result["problem_url"]}')
                return {'folder': folder, 'status': 'completed', 'result': result}
        except Exception as exc:
            message = api.redact(str(exc))
            step = workflow.step if workflow else 'preflight'
            self.log(folder, f'Lỗi tại {step}: {message}')
            if path.exists():
                self.log(folder, f'Sửa riêng bài: python polygon_upload.py resume --state "{path}"')
            return {'folder': folder, 'status': 'failed', 'step': step, 'error': message,
                    'state_path': str(path)}

    @staticmethod
    def _write_problem_result(options, result):
        output = Path(options['output_dir'])
        atomic_json(output / 'result.json', result)
        temporary = output / 'problem_url.txt.tmp'
        temporary.write_text(result['problem_url'] + '\n', encoding='utf-8')
        os.replace(temporary, output / 'problem_url.txt')

    def _save_results(self, rows):
        completed = sum(row['status'] == 'completed' for row in rows)
        failed = sum(row['status'] == 'failed' for row in rows)
        result = {'kind': 'batch', 'total': len(rows), 'completed': completed,
                  'failed': failed, 'pending': len(rows) - completed - failed,
                  'problems': rows}
        output = Path(self.options['output_dir'])
        atomic_json(output / 'result.json', result)
        temporary = output / 'problem_url.txt.tmp'
        temporary.write_text(''.join(row['result']['problem_url'] + '\n' for row in rows
                                     if row['status'] == 'completed'), encoding='utf-8')
        os.replace(temporary, output / 'problem_url.txt')
        return result

    def run(self, key, secret, url_resolver):
        atomic_json(self.path, self.state)
        self.step = 'batch-upload'
        entries = self.state['problems']
        rows = [{'folder': entry['folder'], 'status': 'pending'} for entry in entries]
        self._save_results(rows)
        executor = ThreadPoolExecutor(max_workers=min(self.options['jobs'], len(entries)))
        try:
            futures = {executor.submit(self._run_one, entry, parts, key, secret, url_resolver): index
                       for index, (entry, parts) in enumerate(zip(entries, self.problems))}
            for future in as_completed(futures):
                rows[futures[future]] = future.result()
                self._save_results(rows)
        finally:
            # Stop workers between requests, retaining every in-flight intent in
            # its own checkpoint. HTTP calls already sent finish at their timeout.
            self.cancelled.set()
            executor.shutdown(wait=True, cancel_futures=True)
        result = self._save_results(rows)
        self.log('batch', f'Hoàn tất {result["completed"]}/{result["total"]} bài; lỗi {result["failed"]} bài.')
        return result
