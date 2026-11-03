"""Resumable Polygon workflow with acknowledged source and script uploads."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from .api import APIError, TransportError
from .samples import detect_sample_indices
from .resources import resource_manifest, remove_uploaded_resource


class WorkflowError(RuntimeError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


@contextmanager
def state_lock(path: Path):
    """OS releases the lock on crash, including on Windows; no stale PID guessing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + '.lock').open('a+b') as lock:
        lock.seek(0)
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise WorkflowError('Checkpoint đang được một tiến trình khác sử dụng.') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def text_equal(a: str, b: str) -> bool:
    # Polygon may normalize EOL on storage. No other whitespace is ignored.
    return a.replace('\r\n', '\n') == b.replace('\r\n', '\n')


class Workflow:
    def __init__(self, api, state_path: Path, parts: dict, options: dict,
                 *, resources: dict[str, bytes] | None = None,
                 log: Callable[[str], None] | None = None, sleep=time.sleep,
                 monotonic=time.monotonic):
        self.api, self.path, self.parts, self.options = api, Path(state_path), parts, options
        self.resources = resources or {}
        self.resource_manifest = resource_manifest(self.resources)
        self.log = log or (lambda message: print(message, file=sys.stderr))
        self.sleep, self.clock = sleep, monotonic
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.step = 'preflight'
        self.migrate_upload_receipts()

    def upload_requests(self):
        source_type = self.options.get('source_type', 'cpp.g++17')
        return {
            'checker.cpp': ('problem.saveFile', {'type': 'source', 'name': 'checker.cpp',
                            'file': self.parts['checker'], 'sourceType': source_type}),
            'gen.cpp': ('problem.saveFile', {'type': 'source', 'name': 'gen.cpp',
                        'file': self.parts['gen'], 'sourceType': source_type}),
            'solution': ('problem.saveSolution', {'name': 'solution.cpp', 'file': self.parts['solution'],
                         'sourceType': source_type, 'tag': 'MA'}),
            'script': ('problem.saveScript', {'testset': 'tests', 'source': self.parts['script_sinh_test']}),
        }

    def migrate_upload_receipts(self):
        """Use old completed snapshots once, then stop tracking managed content."""
        if not self.state:
            return
        snapshot = self.state.get('snapshot', {})
        if 'upload_receipts' not in self.state:
            receipts = {}
            if digest(self.parts) == self.state.get('input_digest'):
                completed = {
                    'checker.cpp': 'source:checker.cpp' in snapshot.get('files', {}),
                    'gen.cpp': 'source:gen.cpp' in snapshot.get('files', {}),
                    'solution': 'solution.cpp' in snapshot.get('solutions', {}),
                    'script': bool(snapshot.get('script')),
                }
                for label, done in completed.items():
                    if done and self.state.get('pending') != label:
                        receipts[label] = digest(self.upload_requests()[label])
            self.state['upload_receipts'] = receipts
        snapshot.pop('script', None)
        for name in ('source:checker.cpp', 'source:gen.cpp'):
            snapshot.get('files', {}).pop(name, None)
        snapshot.get('solutions', {}).pop('solution.cpp', None)

    def save(self):
        atomic_json(self.path, self.state)

    def accept_updated_input(self):
        """Explicit correction of the same problem, after checking server ownership."""
        self.step = 'update-input'
        if not self.state.get('problem_id') or 'snapshot' not in self.state:
            raise WorkflowError('Phải xác định problem ID và snapshot trước khi đổi input.')
        if self.state.get('pending'):
            raise WorkflowError('Còn request chưa xác định kết quả; resume xử lý request đó trước khi đổi input.')
        if self.parts['name problem'] != self.state.get('requested_name', self.problem_name):
            raise WorkflowError('Không đổi name problem.txt khi cập nhật cùng problem ID.')
        self.check_revision()  # Also checks slug/owner against the actual object.
        self.verify_snapshot()
        if (digest(self.parts) == self.state['input_digest']
                and self.resource_manifest == self.state.get('resource_manifest', {})):
            raise WorkflowError('Input không đổi; dùng --retry-failed-package nếu muốn thử lại package FAILED.')
        self.state.setdefault('history', []).append({
            'revision': self.state['revision'], 'package_id': self.state.get('package_id'),
            'input_digest': self.state['input_digest']})
        for key in ('committed', 'package_id', 'package_state', 'package_comment',
                    'build_before_ids', 'build_full', 'build_verify', 'completed', 'result', 'resource_cleanup'):
            self.state.pop(key, None)
        self.state.update(input_digest=digest(self.parts), input_path=self.options['input_path'],
                          options=self.options, resource_manifest=self.resource_manifest)
        if self.resources and 'statement_resources' not in self.state['snapshot']:
            self.state['snapshot']['statement_resources'] = self.statement_resource_inventory()
        self.save()

    def retry_failed_package(self):
        """Only an explicit user request may schedule another build after FAILED."""
        self.step = 'retry-package'
        if self.state.get('pending') or not self.state.get('committed') or not self.state.get('package_id'):
            raise WorkflowError('Chỉ thử lại package đã xác định rõ ID và trạng thái FAILED.')
        self.check_revision()
        self.verify_snapshot()
        package = self.tracked_package(self.read('problem.packages'))
        if package['state'] != 'FAILED':
            raise WorkflowError('Package chưa FAILED ở revision đã ghi; không tạo thêm package.')
        self.state.setdefault('history', []).append({
            'revision': self.state['revision'], 'package_id': self.state['package_id'], 'state': 'FAILED'})
        for key in ('package_id', 'package_state', 'package_comment', 'build_before_ids',
                    'build_full', 'build_verify'):
            self.state.pop(key, None)
        self.save()

    def read(self, method, **params):
        return self.api.call(method, {'problemId': self.state['problem_id'], **params})

    def raw(self, method, **params):
        return self.api.call(method, {'problemId': self.state['problem_id'], **params}, raw=True)

    def write(self, method, **params):
        return self.api.call(method, {'problemId': self.state['problem_id'], **params}, mutation=True)

    @property
    def problem_name(self):
        return self.state.get('problem_name', self.parts['name problem'])

    def metadata(self):
        rows = self.api.call('problems.list', {'id': self.state['problem_id']})
        rows = [r for r in rows if r['id'] == self.state['problem_id'] and not r.get('deleted')]
        if len(rows) != 1:
            raise WorkflowError('Không đọc được chính xác problem ID trong checkpoint.')
        row = rows[0]
        if row['name'] != self.problem_name or row['owner'] != self.state['owner']:
            raise WorkflowError('Xung đột danh tính problem; dừng để tránh sửa nhầm bài.')
        return row

    def file_inventory(self):
        result = {}
        groups = self.read('problem.files')
        for category, key in [('source', 'sourceFiles'), ('resource', 'resourceFiles'), ('aux', 'auxFiles')]:
            for item in groups.get(key, []):
                if category == 'source' and item['name'] in ('checker.cpp', 'gen.cpp'):
                    continue
                # Only files outside the four managed uploads remain protected
                # by remote snapshots. Never read managed source contents back.
                meta = dict(item)
                if category == 'source':
                    meta['sha256'] = digest(self.raw('problem.viewFile', type=category, name=item['name']))
                result[f'{category}:{item["name"]}'] = meta
        return result

    def solution_inventory(self):
        return {s['name']: {**s, 'sha256': digest(self.raw('problem.viewSolution', name=s['name']))}
                for s in self.read('problem.solutions') if s['name'] != 'solution.cpp'}

    def statement_resource_inventory(self):
        inventory = {}
        for item in self.read('problem.statementResources'):
            name = item['name']
            if name in inventory:
                raise WorkflowError(f'Polygon trả resource trùng tên: {name}')
            data = self.api.call('problem.viewStatementResource',
                                 {'problemId': self.state['problem_id'], 'name': name}, binary=True)
            inventory[name] = hashlib.sha256(data).hexdigest()
        return inventory

    def snapshot(self):
        info = self.read('problem.info')
        other_settings = {}
        for method in ('problem.interactor', 'problem.extraValidators', 'problem.viewTags',
                       'problem.viewGeneralDescription', 'problem.viewGeneralTutorial',
                       'problem.checkerTests', 'problem.validatorTests', 'problem.materials'):
            # Polygon rejects interactor queries for ordinary (non-interactive) problems.
            value = '' if method == 'problem.interactor' and not info['interactive'] else self.read(method)
            if method in ('problem.checkerTests', 'problem.validatorTests'):
                # Verification updates run results without changing the working copy.
                value = [{k: v for k, v in row.items() if k not in ('runVerdict', 'runComment')}
                         for row in value]
            other_settings[method] = value
        resource_snapshot = {}
        if self.state.get('resource_manifest') or 'statement_resources' in self.state.get('snapshot', {}):
            resource_snapshot['statement_resources'] = self.statement_resource_inventory()
        return {
            **resource_snapshot,
            'info': info,
            'statements': self.read('problem.statements'),
            'files': self.file_inventory(),
            'solutions': self.solution_inventory(),
            'tests': self.read('problem.tests', testset='tests', noInputs=True),
            'checker': self.read('problem.checker'),
            'validator': self.read('problem.validator'),
            'accesses': self.read('problem.accesses'),
            'other_settings': other_settings,
        }

    def check_revision(self):
        meta = self.metadata()
        expected = self.state.get('revision')
        if expected is not None and meta['revision'] != expected:
            raise WorkflowError('Revision đã thay đổi ngoài công cụ. Không tự cập nhật/xóa working copy.')
        wc = meta.get('workingCopyRevision')
        if wc is not None and wc != meta['revision']:
            raise WorkflowError('Working copy lỗi thời; cần giải quyết trên Polygon trước khi resume.')
        return meta

    @staticmethod
    def duplicate_name_error(error, name):
        # Only explicit name-collision replies authorize another create. Network
        # errors (even those containing similar words) must be reconciled.
        if (isinstance(error, TransportError) or error.ambiguous
                or error.method != 'problem.create' or error.status_code not in (200, 400, 409)):
            return False
        message = str(error).removeprefix('problem.create: ').strip()
        patterns = (
            r'(?:name:\s*)?(?:a )?problem with (?:this |the same |such (?:a )?)?name already exists[.!]?',
            r'(?:name:\s*)?(?:problem )?name (?:already exists|is already (?:used|taken|in use))[.!]?',
            r'(?:name:\s*)?(?:a )?problem with name [\"\']?' + re.escape(name) + r'[\"\']? already exists[.!]?',
        )
        return any(re.fullmatch(pattern, message, re.IGNORECASE) for pattern in patterns)

    def next_problem_name(self):
        previous = self.problem_name
        self.state.update(problem_name=previous + '1', pending='select-name')
        self.state.pop('create_before_ids', None)
        self.save()
        self.log(f'Tên {previous} đã tồn tại. Thử {self.problem_name}...')

    def create_or_recover(self):
        self.step = 'create'
        if 'problem_id' in self.state:
            return
        if not self.state:
            self.state = {'version': 1, 'input_path': self.options['input_path'],
                          'input_digest': digest(self.parts), 'options': self.options,
                          'resource_manifest': self.resource_manifest,
                          'requested_name': self.parts['name problem'],
                          'problem_name': self.parts['name problem'],
                          'pending': 'select-name', 'upload_receipts': {}}
            self.save()
        while self.state.get('pending') == 'select-name':
            existing = self.api.call('problems.list', {'name': self.problem_name})
            if any(r['name'] == self.problem_name and not r.get('deleted') for r in existing):
                self.next_problem_name()
                continue
            self.state.update(create_before_ids=[r['id'] for r in existing], pending='create')
            self.save()  # Durable name and intent BEFORE the non-idempotent call.
            try:
                result = self.api.call('problem.create', {'name': self.problem_name}, mutation=True)
            except APIError as exc:
                if not self.duplicate_name_error(exc, self.problem_name):
                    raise
                self.next_problem_name()
                continue
            self.bind_created(result)
            return
        # A lost create response is not proof that a same-name object belongs to us.
        candidates = self.api.call('problems.list', {'name': self.problem_name})
        candidates = [p for p in candidates if p['id'] not in self.state['create_before_ids']
                      and p['name'] == self.problem_name and not p.get('deleted')]
        chosen = self.options.get('problem_id')
        matches = [p for p in candidates if p['id'] == chosen and p.get('accessType') == 'OWNER']
        if chosen and len(matches) == 1:
            self.bind_created(matches[0])
            return
        raise WorkflowError('Chưa xác định kết quả tạo bài; không gửi lại problem.create. '
                            f'Tên đang xác minh: {self.problem_name}. '
                            f'Các ID mới cùng tên: {[p["id"] for p in candidates]}. '
                            'Kiểm tra bài trên Polygon, rồi resume --problem-id ID nếu đúng bài vừa tạo.')

    def bind_created(self, problem):
        if not isinstance(problem, dict) or not isinstance(problem.get('id'), int):
            raise WorkflowError('Phản hồi tạo bài thiếu ID; giữ checkpoint để kiểm tra server.')
        if problem.get('name', self.problem_name) != self.problem_name:
            raise WorkflowError('Phản hồi tạo bài sai tên; giữ checkpoint để kiểm tra server.')
        self.state.update(problem_name=self.problem_name,
                          requested_name=self.state.get('requested_name', self.parts['name problem']),
                          problem_id=problem['id'], owner=problem['owner'],
                          revision=problem['revision'], pending=None)
        self.save()  # ID persisted before ANY further read or write.
        self.log(f'Đã tạo bài {self.problem_name}, ID: {problem["id"]}.')

    def initialize_snapshot(self):
        if 'snapshot' not in self.state:
            self.step = 'snapshot'
            self.check_revision()
            self.state['snapshot'] = self.snapshot()
            self.save()

    @staticmethod
    def verify_scope(method, params, previous, current):
        """A completed request cannot authorize unrelated concurrent changes."""
        before, after = json.loads(json.dumps(previous)), json.loads(json.dumps(current))
        if method == 'problem.updateInfo':
            for key in params:
                before['info'].pop(key, None)
                after['info'].pop(key, None)
        elif method == 'problem.saveStatement':
            lang = params['lang']
            old = before['statements'].pop(lang, None)
            new = after['statements'].pop(lang, None)
            if old is not None:
                old, new = dict(old), dict(new or {})
                for key in params:
                    if key != 'lang':
                        old.pop(key, None)
                        new.pop(key, None)
                if old != new:
                    raise WorkflowError('Xung đột trường statement ngoài nội dung đang lưu.')
        elif method == 'problem.saveTest':
            for row in before['tests']:
                if row['index'] == params['testIndex']:
                    row['useInStatements'] = params['testUseInStatements']
        elif method == 'problem.setAccess':
            before['accesses'] = [a for a in before['accesses'] if a['login'] != params['login']]
            after['accesses'] = [a for a in after['accesses'] if a['login'] != params['login']]
        elif method == 'problem.setChecker':
            before.pop('checker')
            after.pop('checker')
        if before != after:
            raise WorkflowError(f'Xung đột thay đổi ngoài phạm vi request {method}.')

    def action(self, label, method, params, sections, readers, satisfied, *, mismatch_details=None):
        """Compare-before-write and verify-after-write. Pending writes are reconciled."""
        def mismatch_error(message):
            details = mismatch_details() if mismatch_details else []
            return WorkflowError(message + (' ' + ' '.join(details) if details else ''))

        self.step = label
        self.check_revision()
        pending = self.state.get('pending')
        if pending and pending != label:
            # Earlier completed actions remain readable while a later action is pending.
            if not satisfied():
                raise mismatch_error(f'Xung đột bước {label}; đang chờ xử lý {pending}.')
            return
        current = {key: reader() for key, reader in zip(sections, readers)}
        previous = {key: self.state['snapshot'][key] for key in sections}
        if pending == label:
            if satisfied():
                self.verify_scope(method, params, previous, current)
                self.state['snapshot'].update(current)
                self.state['pending'] = None
                self.save()
                return
            if current != previous:
                raise mismatch_error(f'Bước {label} chưa hoàn tất và dữ liệu đã khác checkpoint; cần kiểm tra trên Polygon.')
        elif current != previous:
            # The user may have completed "Set checker" in the web UI while
            # stopped. Adopt only the requested selection; other changes still
            # go through the normal scope and final snapshot checks.
            if method == 'problem.setChecker' and satisfied():
                self.verify_scope(method, params, previous, current)
                self.state['snapshot'].update(current)
                self.save()
                return
            raise WorkflowError(f'Xung đột thay đổi bên ngoài tại {label}; không ghi đè.')
        if satisfied():
            return
        self.log(f'Đang lưu: {label}')
        self.state['pending'] = label
        self.save()
        try:
            self.write(method, **params)
        except APIError:
            # Keep intent: even a server failure may have partially changed state.
            raise
        if not satisfied():
            raise mismatch_error(f'{label}: đọc lại không khớp dữ liệu đã gửi.')
        updated = {key: reader() for key, reader in zip(sections, readers)}
        self.verify_scope(method, params, previous, updated)
        self.state['snapshot'].update(updated)
        self.state['pending'] = None
        self.save()

    def upload_without_readback(self, label):
        """An API success acknowledges these named uploads; no content read-back."""
        self.step = label
        self.check_revision()
        method, params = self.upload_requests()[label]
        receipt = digest((method, params))
        receipts = self.state.setdefault('upload_receipts', {})
        if receipts.get(label) == receipt:
            return
        pending = self.state.get('pending')
        if pending and pending != label:
            raise WorkflowError(f'Chưa hoàn tất {label}; đang chờ xử lý {pending}.')
        if label in ('checker.cpp', 'gen.cpp', 'solution'):
            section = 'solutions' if label == 'solution' else 'files'
            current = self.solution_inventory() if label == 'solution' else self.file_inventory()
            if current != self.state['snapshot'][section]:
                raise WorkflowError(f'Xung đột thay đổi ngoài các file đang tải tại {label}.')
        self.log(f'Đang lưu: {label}')
        self.state['pending'] = label
        self.save()
        # If an earlier response was lost, replay only this named save operation.
        # problem.create, commits and package builds retain their own recovery.
        self.write(method, **params)
        if label == 'script':
            tests = self.read('problem.tests', testset='tests', noInputs=True)
            manual = lambda rows: [row for row in rows if row.get('manual')]
            if manual(tests) != manual(self.state['snapshot']['tests']):
                raise WorkflowError('Xung đột test thủ công ngoài script đang lưu.')
            self.state['snapshot']['tests'] = tests
        receipts[label] = receipt
        self.state['pending'] = None
        self.save()

    def activate_checker(self):
        selected = []

        def checker_ok():
            selected[:] = [self.read('problem.checker')]
            return selected[0] == 'checker.cpp'

        self.action('checker', 'problem.setChecker', {'checker': 'checker.cpp'}, ['checker'],
                    [lambda: self.read('problem.checker')], checker_ok,
                    mismatch_details=lambda: [
                        f'Checker cần dùng: checker.cpp; Polygon đang chọn: {selected[0]!r}.'])
        self.log('Đã xác nhận checker đang dùng trên Polygon: checker.cpp.')

    def upload_resources(self):
        for index, (name, data) in enumerate(self.resources.items(), 1):
            label = 'resource:' + name
            self.step = label
            self.check_revision()
            self.log(f'Resource [{index}/{len(self.resources)}]: {name}')
            expected = self.resource_manifest[name]
            snapshot = self.state['snapshot']['statement_resources']

            def current_hash():
                if not any(item['name'] == name for item in self.read('problem.statementResources')):
                    return None
                content = self.api.call('problem.viewStatementResource',
                                        {'problemId': self.state['problem_id'], 'name': name}, binary=True)
                return hashlib.sha256(content).hexdigest()

            current = current_hash()
            pending = self.state.get('pending')
            if pending and pending != label:
                if current != expected:
                    raise WorkflowError(f'Xung đột {label}; đang chờ xử lý {pending}.')
                continue
            if pending == label and current == expected:
                snapshot[name] = expected
                self.state['pending'] = None
                self.save()
                continue
            if current != snapshot.get(name):
                raise WorkflowError(f'Xung đột thay đổi bên ngoài tại {label}; không ghi đè.')
            if current == expected:
                continue
            self.state['pending'] = label
            self.save()
            self.write('problem.saveStatementResource', name=name, file=data)
            if current_hash() != expected:
                raise WorkflowError(f'{label}: đọc lại không khớp dữ liệu đã gửi.')
            # Only acknowledge this file. Full snapshot checks before commit
            # and completion still detect unrelated edits without downloading
            # every other resource again for each uploaded file.
            snapshot[name] = expected
            self.state['pending'] = None
            self.save()

    def upload(self):
        p = self.parts
        info_updates = {k: self.options[k] for k in ('timeLimit', 'memoryLimit', 'inputFile', 'outputFile')
                        if self.options.get(k) is not None}
        self.action('info', 'problem.updateInfo', info_updates, ['info'],
                    [lambda: self.read('problem.info')],
                    lambda: all(self.read('problem.info').get(k) == v for k, v in info_updates.items()))
        self.log('Giới hạn/tệp thực tế: ' + json.dumps(self.read('problem.info'), ensure_ascii=False))
        statement = {'name': p['name'], 'legend': p['lengend'], 'input': p['input'],
                     'output': p['output'], 'notes': p['note']}
        def statement_ok():
            got = self.read('problem.statements').get('vietnamese', {})
            return all(isinstance(got.get(k), str) and text_equal(got[k], v) for k, v in statement.items())
        self.action('statement', 'problem.saveStatement', {'lang': 'vietnamese', 'encoding': 'UTF-8', **statement},
                    ['statements'], [lambda: self.read('problem.statements')], statement_ok)
        self.upload_resources()
        self.upload_without_readback('checker.cpp')
        # Old checkpoints can have an unresolved generator write before checker
        # selection. Reconcile that write first, without replacing its intent.
        defer_checker = self.state.get('pending') == 'gen.cpp'
        if not defer_checker:
            self.activate_checker()
        self.upload_without_readback('gen.cpp')
        if defer_checker:
            self.activate_checker()
        solutions = self.read('problem.solutions')
        if any(s.get('tag') == 'MA' and s['name'] != 'solution.cpp' for s in solutions):
            raise WorkflowError('Có lời giải chính khác; không tự đổi tag hoặc xóa lời giải đó.')
        self.upload_without_readback('solution')
        if any(re.search(r'#\s*include\s*[<"]testlib\.h[>"]', p[part]) for part in ('checker', 'gen', 'solution')):
            resources = self.read('problem.files').get('resourceFiles', [])
            if not any(f['name'] == 'testlib.h' for f in resources):
                self.log('testlib.h không có trong resourceFiles; sẽ kiểm tra hỗ trợ thư viện qua build có verify=true.')
            else:
                self.log('Đã xác nhận resource testlib.h trên Polygon.')
        self.upload_without_readback('script')
        self.mark_samples()
        def access_ok():
            return any(a['login'] == 'codeforces' and a['accessType'] in ('READ', 'WRITE', 'OWNER')
                       for a in self.read('problem.accesses'))
        self.action('access', 'problem.setAccess', {'login': 'codeforces', 'accessType': 'READ'},
                    ['accesses'], [lambda: self.read('problem.accesses')], access_ok)

    def mark_samples(self):
        """Mark every actual expanded sample index, then verify the complete set."""
        self.step = 'samples'
        tests = self.read('problem.tests', testset='tests', noInputs=True)
        samples = detect_sample_indices(tests, self.options.get('sample_indices'))
        expected = set(samples)
        pending = self.state.get('pending')
        if (pending and pending.startswith('sample:')
                and pending not in {f'sample:{test["index"]}' for test in tests}):
            raise WorkflowError(f'Test của bước {pending} đã biến mất; không bỏ qua request chưa xác minh.')
        # One list read already tells us which flags match. Calling action() for
        # every unchanged test used to cost three API requests per test. Still
        # reconcile a pending sample even when its flag now has the desired value.
        changes = [test for test in tests
                   if test.get('useInStatements') is not (test['index'] in expected)
                   or pending == f'sample:{test["index"]}']
        self.log(f'Example: {len(samples)} sample trong {len(tests)} test; '
                 f'cần cập nhật/xác minh {len(changes)} test.')
        for position, test in enumerate(changes, 1):
            index, flag = test['index'], test['index'] in expected
            self.log(f'Example [{position}/{len(changes)}]: test {index}, '
                     + ('bật' if flag else 'tắt') + ' Example.')
            def flag_ok(index=index, flag=flag):
                rows = self.read('problem.tests', testset='tests', noInputs=True)
                return any(t['index'] == index and t.get('useInStatements') is flag for t in rows)
            self.action(f'sample:{index}', 'problem.saveTest', {'testset': 'tests', 'testIndex': index,
                        'testUseInStatements': flag}, ['tests'],
                        [lambda: self.read('problem.tests', testset='tests', noInputs=True)], flag_ok)
        self.step = 'samples'
        self.log(f'Đang đọc lại toàn bộ {len(tests)} test để xác nhận Example...')
        self.verify_samples(required=samples)
        confirmed = self.state['sample_indices']
        self.log(f'Đã xác nhận Example cho tất cả {len(confirmed)} test sample: '
                 + ', '.join(map(str, confirmed)) + '.')

    def verify_samples(self, required=None):
        """Never commit/build/report success with a sample missing Example."""
        tests = self.read('problem.tests', testset='tests', noInputs=True)
        required = self.state.get('sample_indices', []) if required is None else required
        marked = {test['index'] for test in tests if test.get('useInStatements') is True}
        missing_required = sorted(set(required) - marked)
        if missing_required:
            raise WorkflowError('Test sample chưa bật Example hoặc đã biến mất: '
                                + ', '.join(map(str, missing_required)) + '.')
        samples = detect_sample_indices(tests, self.options.get('sample_indices'))
        expected = set(samples) | set(required)
        missing = [test['index'] for test in tests
                   if test['index'] in expected and test.get('useInStatements') is not True]
        invalid = [test['index'] for test in tests
                   if test['index'] not in expected and test.get('useInStatements') is not False]
        if missing or invalid:
            details = []
            if missing:
                details.append('Test sample chưa bật Example: ' + ', '.join(map(str, sorted(missing))) + '.')
            if invalid:
                details.append('Cờ Example không đúng ở test thường: '
                               + ', '.join(map(str, sorted(invalid))) + '.')
            raise WorkflowError(' '.join(details) + ' Chưa thể xác nhận đầy đủ Example trên Polygon.')
        # Skipped unchanged flags still need one whole-list conflict check:
        # generator lines, groups, and other test metadata must match too.
        if tests != self.state['snapshot']['tests']:
            raise WorkflowError('Xung đột dữ liệu test ngoài checkpoint; không tiếp tục commit/build.')
        self.state.update(sample_indices=sorted(expected), test_count=len(tests))
        self.save()

    def verify_snapshot(self):
        current = self.snapshot()
        changed = [k for k in current if current[k] != self.state['snapshot'][k]]
        if changed:
            raise WorkflowError('Xung đột dữ liệu ngoài checkpoint: ' + ', '.join(changed))

    def commit(self):
        self.step = 'commit'
        self.verify_samples()
        self.verify_snapshot()
        meta = self.metadata()
        if self.state.get('pending') == 'commit':
            if meta['revision'] == self.state['revision'] + 1 and not meta['modified']:
                self.state.update(revision=meta['revision'], committed=True, pending=None)
                self.save()
                return
            if meta['revision'] != self.state['revision'] or not meta['modified']:
                raise WorkflowError('Không xác định được commit bị gián đoạn; kiểm tra revision trên Polygon.')
        else:
            self.check_revision()
        if self.state.get('committed'):
            if meta['modified']:
                raise WorkflowError('Có thay đổi chưa commit sau checkpoint đã commit.')
            return
        cautions = self.read('problem.cautions')
        blockers = [i for i in cautions.get('packageReadinessIssues', []) if i['type'] != 'HAS_MODIFICATIONS']
        if blockers:
            raise WorkflowError('Polygon chưa sẵn sàng: ' + '; '.join(i['message'] for i in blockers))
        self.state['pending'] = 'commit'
        self.save()
        result = self.write('problem.commitChanges', minorChanges=True, message='Upload with polygon_upload')
        if not isinstance(result, dict) or result.get('conflictOccurred') or not result.get('committed'):
            raise WorkflowError('Commit không được xác nhận: ' + str(result))
        meta = self.metadata()
        if meta['modified'] or meta['revision'] != self.state['revision'] + 1:
            raise WorkflowError('Commit chưa tạo revision mới sạch; giữ checkpoint.')
        self.state.update(revision=meta['revision'], committed=True, pending=None)
        self.save()
        self.log(f'Đã commit revision {meta["revision"]}.')

    def tracked_package(self, packages):
        """Find the standard descriptor of the saved build, including Full builds."""
        matches = [p for p in packages if p['id'] == self.state['package_id']]
        if not matches:
            raise WorkflowError('Không tìm thấy package ID đã ghi; không build thêm.')
        if any(p['revision'] != self.state['revision'] for p in matches):
            raise WorkflowError('Package không thuộc revision đã commit; không build thêm.')
        # A completed Full build exposes standard/linux/windows with the same ID.
        # Identify the archive by (id, type), as in pending-build recovery and ZIP
        # downloads; multiple archive types do not mean the build is missing.
        standard = [p for p in matches if p['type'] == 'standard']
        if not standard:
            raise WorkflowError('Không tìm thấy bản ZIP standard của package ID đã ghi; không build thêm.')
        if len(standard) != 1:
            raise WorkflowError('Có nhiều bản ghi ZIP standard của package ID đã ghi; không build thêm.')
        return standard[0]

    def package(self):
        self.step = 'package'
        if not self.state.get('committed'):
            raise WorkflowError('Chưa xác nhận Commit Changes thành công; không tạo package.')
        self.verify_samples()
        meta = self.check_revision()
        if meta['modified']:
            raise WorkflowError('Không build khi working copy còn thay đổi chưa commit.')
        packages = self.read('problem.packages')
        revision = self.state['revision']
        if self.state.get('pending') == 'build' and not self.state.get('package_id'):
            candidates = [p for p in packages if p['id'] not in self.state['build_before_ids']
                          and p['revision'] == revision and p['type'] == 'standard']
            selected = self.options.get('package_id')
            if selected:
                candidates = [p for p in candidates if p['id'] == selected]
            if len(candidates) != 1:
                raise WorkflowError('Chưa xác định package sau request bị gián đoạn; không build lặp. '
                                    f'Ứng viên: {[p["id"] for p in candidates]}. Kiểm tra rồi resume --package-id ID.')
            self.state.update(package_id=candidates[0]['id'], pending=None)
            self.save()
        if not self.state.get('package_id'):
            cautions = self.read('problem.cautions')
            blockers = cautions.get('packageReadinessIssues', [])
            if blockers:
                raise WorkflowError('Polygon chặn package: ' + '; '.join(i['message'] for i in blockers))
            # Full is a build option, not a package archive type. A Full build
            # includes standard/linux/windows; track its standard descriptor ID.
            # Persist the requested mode BEFORE sending the non-idempotent call.
            self.state.update(pending='build', build_before_ids=[p['id'] for p in packages],
                              build_full=True, build_verify=True)
            self.save()
            self.log(f'Đang tạo package Full (Verify bật) cho revision {revision} đã commit.')
            result = self.write('problem.buildPackage', full=True, verify=True)
            # Some versions return no result. Reconcile the list, never repeat build.
            if isinstance(result, dict) and isinstance(result.get('id'), int):
                if result.get('revision') != revision or result.get('type') != 'standard':
                    raise WorkflowError('Build trả về package sai revision/type.')
                self.state.update(package_id=result['id'], pending=None)
                self.save()
            else:
                return self.package()
        deadline = self.clock() + self.options.get('poll_timeout', 900)
        while True:
            self.check_revision()
            rows = self.read('problem.packages')
            package = self.tracked_package(rows)
            self.state['package_state'] = package['state']
            self.state['package_comment'] = package.get('comment', '')
            self.save()
            if not self.state.get('build_full') and package['state'] in ('READY', 'FAILED'):
                # Older checkpoints requested Standard only. First reconcile and
                # finish that exact job, then deliberately request Full once on
                # the same committed revision. Never repeat an ambiguous build.
                self.verify_snapshot()
                self.state.setdefault('history', []).append({
                    'revision': revision, 'package_id': package['id'],
                    'state': package['state'], 'build_full': False})
                for key in ('package_id', 'package_state', 'package_comment', 'build_before_ids',
                            'build_full', 'build_verify', 'completed', 'result'):
                    self.state.pop(key, None)
                self.options.pop('package_id', None)
                self.state['options'] = self.options
                self.save()
                self.log(f'Package Standard cũ {package["id"]} đã kết thúc; chuyển sang tạo Full.')
                return self.package()
            if package['state'] == 'FAILED':
                raise WorkflowError('Package FAILED: ' + package.get('comment', '(Polygon không trả chi tiết)'))
            if package['state'] == 'READY':
                self.log(f'Package Full {package["id"]} READY (Verify bật).')
                return package
            if package['state'] not in ('PENDING', 'RUNNING'):
                raise WorkflowError('Trạng thái package không nhận diện: ' + str(package['state']))
            if self.clock() >= deadline:
                raise WorkflowError('Hết thời gian chờ package; resume tiếp tục poll cùng package ID.')
            self.log(f'Package {package["id"]}: {package["state"]}')
            self.sleep(min(self.options.get('poll_interval', 5), max(0, deadline - self.clock())))

    def finish_resource_cleanup(self):
        """Called only after saved results; a durable per-file queue survives crashes."""
        if not self.state.get('completed') or not self.state.get('result'):
            raise WorkflowError('Chưa lưu kết quả hoàn tất; không xóa resource.')
        if not self.options.get('resource_path') or not self.state.get('resource_manifest'):
            return
        self.step = 'resource-cleanup'
        if 'resource_cleanup' not in self.state:
            self.state['resource_cleanup'] = {
                'directory': self.options['resource_path'],
                'pending': list(self.state['resource_manifest']), 'removed': [], 'kept': []}
            self.save()  # Durable cleanup intent before deleting the first file.
        cleanup = self.state['resource_cleanup']
        output = Path(self.options.get('output_dir', '.'))
        protected = {self.path.resolve(), self.path.with_name(self.path.name + '.lock').resolve(),
                     (output / 'result.json').resolve(), (output / 'problem_url.txt').resolve()}
        while cleanup['pending']:
            name = cleanup['pending'][0]
            outcome = remove_uploaded_resource(
                Path(cleanup['directory']), name, self.state['resource_manifest'][name],
                protected=protected, input_directory=Path(self.options['input_path']))
            if outcome == 'kept':
                cleanup['kept'].append(name)
                self.log(f'Giữ resource đã thay đổi hoặc được bảo vệ: {name}')
            else:
                cleanup['removed'].append(name)
                self.log(f'Đã dọn resource: {name}')
            cleanup['pending'].pop(0)
            self.save()

    def run(self, url_resolver):
        if self.state and self.resource_manifest != self.state.get('resource_manifest', {}):
            raise WorkflowError('Resource khác checkpoint. Khôi phục resource cũ hoặc dùng resume --update-input để chủ động cập nhật.')
        if self.state and self.state.get('input_digest') != digest(self.parts):
            raise WorkflowError('Nội dung input khác checkpoint. Không tiếp tục ghi đè bài đang chạy.')
        self.create_or_recover()
        self.initialize_snapshot()
        # A pending commit may already have increased revision; reconcile before upload checks.
        if self.state.get('pending') == 'commit':
            self.commit()
        if not self.state.get('committed'):
            self.upload()
            self.commit()
        else:
            self.check_revision()
            self.verify_snapshot()
        package = self.package()
        self.step = 'url'
        problem = self.metadata()
        problem['revision'] = self.state['revision']
        url = url_resolver(self.api, problem, package['id'], browser=self.options.get('browser', False),
                           profile=Path(self.options.get('browser_profile', '.polygon-browser')),
                           timeout=self.options.get('browser_timeout', 300))
        self.check_revision()
        self.verify_snapshot()
        self.verify_samples()
        access = next(a['accessType'] for a in self.read('problem.accesses') if a['login'] == 'codeforces')
        result = {'problem_id': self.state['problem_id'], 'name': self.problem_name,
                  'requested_name': self.state.get('requested_name', self.parts['name problem']),
                  'display_name': self.parts['name'], 'statement_language': 'vietnamese',
                  'test_count': self.state['test_count'], 'sample_indices': self.state['sample_indices'],
                  'codeforces_access': access, 'revision': self.state['revision'],
                  'package_id': package['id'], 'package_state': package['state'], 'problem_url': url,
                  'package_full': self.state['build_full'], 'package_verify': self.state['build_verify'],
                  'info': self.read('problem.info')}
        output = Path(self.options.get('output_dir', '.'))
        atomic_json(output / 'result.json', result)
        output.mkdir(parents=True, exist_ok=True)
        tmp = output / 'problem_url.txt.tmp'
        tmp.write_text(url + '\n', encoding='utf-8')
        os.replace(tmp, output / 'problem_url.txt')
        self.state.update(completed=True, result=result, pending=None)
        self.save()
        return result
