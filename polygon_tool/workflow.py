"""Verified, resumable Polygon workflow. Remote writes are never blindly retried."""
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


def source_text_equal(a: str, b: str) -> bool:
    """Allow a single terminal EOL difference when verifying C++ source files."""
    a, b = a.replace('\r\n', '\n'), b.replace('\r\n', '\n')
    return a == b or a == b + '\n' or b == a + '\n'


class Workflow:
    def __init__(self, api, state_path: Path, parts: dict, options: dict,
                 *, log: Callable[[str], None] | None = None, sleep=time.sleep,
                 monotonic=time.monotonic):
        self.api, self.path, self.parts, self.options = api, Path(state_path), parts, options
        self.log = log or (lambda message: print(message, file=sys.stderr))
        self.sleep, self.clock = sleep, monotonic
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.step = 'preflight'

    def save(self):
        atomic_json(self.path, self.state)

    def accept_updated_input(self):
        """Explicit correction of the same problem, after checking server ownership."""
        self.step = 'update-input'
        if not self.state.get('problem_id') or 'snapshot' not in self.state:
            raise WorkflowError('Phải xác định problem ID và snapshot trước khi đổi input.')
        if self.state.get('pending'):
            raise WorkflowError('Còn request chưa xác định kết quả; resume xử lý request đó trước khi đổi input.')
        self.check_revision()  # Also checks slug/owner against the actual object.
        self.verify_snapshot()
        if digest(self.parts) == self.state['input_digest']:
            raise WorkflowError('Input không đổi; dùng --retry-failed-package nếu muốn thử lại package FAILED.')
        self.state.setdefault('history', []).append({
            'revision': self.state['revision'], 'package_id': self.state.get('package_id'),
            'input_digest': self.state['input_digest']})
        for key in ('committed', 'package_id', 'package_state', 'package_comment',
                    'build_before_ids', 'completed', 'result'):
            self.state.pop(key, None)
        self.state.update(input_digest=digest(self.parts), input_path=self.options['input_path'],
                          options=self.options)
        self.save()

    def retry_failed_package(self):
        """Only an explicit user request may schedule another build after FAILED."""
        self.step = 'retry-package'
        if self.state.get('pending') or not self.state.get('committed') or not self.state.get('package_id'):
            raise WorkflowError('Chỉ thử lại package đã xác định rõ ID và trạng thái FAILED.')
        self.check_revision()
        self.verify_snapshot()
        rows = [p for p in self.read('problem.packages') if p['id'] == self.state['package_id']]
        if len(rows) != 1 or rows[0]['state'] != 'FAILED' or rows[0]['revision'] != self.state['revision']:
            raise WorkflowError('Package chưa FAILED ở revision đã ghi; không tạo thêm package.')
        self.state.setdefault('history', []).append({
            'revision': self.state['revision'], 'package_id': self.state['package_id'], 'state': 'FAILED'})
        for key in ('package_id', 'package_state', 'package_comment', 'build_before_ids'):
            self.state.pop(key, None)
        self.save()

    def read(self, method, **params):
        return self.api.call(method, {'problemId': self.state['problem_id'], **params})

    def raw(self, method, **params):
        return self.api.call(method, {'problemId': self.state['problem_id'], **params}, raw=True)

    def write(self, method, **params):
        return self.api.call(method, {'problemId': self.state['problem_id'], **params}, mutation=True)

    def metadata(self):
        rows = self.api.call('problems.list', {'id': self.state['problem_id']})
        rows = [r for r in rows if r['id'] == self.state['problem_id'] and not r.get('deleted')]
        if len(rows) != 1:
            raise WorkflowError('Không đọc được chính xác problem ID trong checkpoint.')
        row = rows[0]
        if row['name'] != self.parts['name problem'] or row['owner'] != self.state['owner']:
            raise WorkflowError('Xung đột danh tính problem; dừng để tránh sửa nhầm bài.')
        return row

    def file_inventory(self):
        result = {}
        groups = self.read('problem.files')
        for category, key in [('source', 'sourceFiles'), ('resource', 'resourceFiles'), ('aux', 'auxFiles')]:
            for item in groups.get(key, []):
                # Text sources are verified byte-for-byte via viewFile; binary resources
                # are tracked by metadata and never downloaded as text or rewritten.
                meta = dict(item)
                if category == 'source':
                    meta['sha256'] = digest(self.raw('problem.viewFile', type=category, name=item['name']))
                result[f'{category}:{item["name"]}'] = meta
        return result

    def solution_inventory(self):
        return {s['name']: {**s, 'sha256': digest(self.raw('problem.viewSolution', name=s['name']))}
                for s in self.read('problem.solutions')}

    def source_mismatches(self, filename, expected_content, source_type, *, solution=False):
        """Explain a failed read-back without printing source code or credentials."""
        rows = (self.read('problem.solutions') if solution else
                self.read('problem.files').get('sourceFiles', []))
        issues = []
        if solution:
            mains = [row for row in rows if row.get('tag') == 'MA']
            if len(mains) != 1 or mains[0]['name'] != filename:
                issues.append(f'{filename} phải là lời giải chính duy nhất (tag MA).')
        matches = [row for row in rows if row['name'] == filename]
        if len(matches) != 1:
            return issues + [f'Không tìm thấy đúng một file {filename} trên Polygon.']
        actual_type = matches[0].get('sourceType')
        if actual_type != source_type:
            issues.append(f'sourceType: cần {source_type!r}, Polygon trả {actual_type!r}.')
        actual_content = (self.raw('problem.viewSolution', name=filename) if solution else
                          self.raw('problem.viewFile', type='source', name=filename))
        if not source_text_equal(actual_content, expected_content):
            expected = expected_content.replace('\r\n', '\n')
            actual = actual_content.replace('\r\n', '\n')
            offset = next((i for i, (a, b) in enumerate(zip(expected, actual)) if a != b),
                          min(len(expected), len(actual)))
            line = expected.count('\n', 0, offset) + 1
            column = offset - expected.rfind('\n', 0, offset)
            issues.append('Nội dung khác sau khi chuẩn hóa CRLF/LF: '
                          f'local {len(expected.encode("utf-8"))} byte, '
                          f'Polygon {len(actual.encode("utf-8"))} byte; '
                          f'vị trí khác đầu tiên: dòng {line}, cột {column}.')
        return issues

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
        return {
            'info': info,
            'statements': self.read('problem.statements'),
            'files': self.file_inventory(),
            'solutions': self.solution_inventory(),
            'script': self.raw('problem.script', testset='tests'),
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

    def create_or_recover(self):
        self.step = 'create'
        if 'problem_id' in self.state:
            return
        if not self.state:
            existing = self.api.call('problems.list', {'name': self.parts['name problem']})
            if any(r['name'] == self.parts['name problem'] and not r.get('deleted') for r in existing):
                raise WorkflowError('Đã có bài cùng tên. Hãy dùng checkpoint của bài đó hoặc chọn tên mới; không ghi đè theo tên.')
            self.state = {'version': 1, 'input_path': self.options['input_path'],
                          'input_digest': digest(self.parts), 'options': self.options,
                          'create_before_ids': [r['id'] for r in existing], 'pending': 'create'}
            self.save()  # Durable intent BEFORE the non-idempotent request.
            result = self.api.call('problem.create', {'name': self.parts['name problem']}, mutation=True)
            self.bind_created(result)
            return
        # A lost create response is not proof that a same-name object belongs to us.
        candidates = self.api.call('problems.list', {'name': self.parts['name problem']})
        candidates = [p for p in candidates if p['id'] not in self.state['create_before_ids']
                      and p['name'] == self.parts['name problem'] and not p.get('deleted')]
        chosen = self.options.get('problem_id')
        matches = [p for p in candidates if p['id'] == chosen and p.get('accessType') == 'OWNER']
        if chosen and len(matches) == 1:
            self.bind_created(matches[0])
            return
        raise WorkflowError('Chưa xác định kết quả tạo bài; không gửi lại problem.create. '
                            f'Các ID mới cùng tên: {[p["id"] for p in candidates]}. '
                            'Kiểm tra bài trên Polygon, rồi resume --problem-id ID nếu đúng bài vừa tạo.')

    def bind_created(self, problem):
        if not isinstance(problem, dict) or not isinstance(problem.get('id'), int):
            raise WorkflowError('Phản hồi tạo bài thiếu ID; giữ checkpoint để kiểm tra server.')
        self.state.update(problem_id=problem['id'], owner=problem['owner'],
                          revision=problem['revision'], pending=None)
        self.save()  # ID persisted before ANY further read or write.

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
        elif method in ('problem.saveFile', 'problem.saveSolution'):
            section = 'files' if method == 'problem.saveFile' else 'solutions'
            key = f'{params["type"]}:{params["name"]}' if section == 'files' else params['name']
            before[section].pop(key, None)
            after[section].pop(key, None)
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
        elif method == 'problem.saveScript':
            # Generated rows are server expansion (including FreeMarker).
            # A script write does not authorize changes to manual tests.
            before.pop('script')
            after.pop('script')
            before['tests'] = [t for t in before['tests'] if t.get('manual')]
            after['tests'] = [t for t in after['tests'] if t.get('manual')]
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

    def upload(self):
        p = self.parts
        source_type = self.options.get('source_type', 'cpp.g++17')
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
        def upload_source(filename, part):
            mismatches = []
            def file_ok():
                mismatches[:] = self.source_mismatches(filename, p[part], source_type)
                return not mismatches
            self.action(filename, 'problem.saveFile', {'type': 'source', 'name': filename,
                        'file': p[part], 'sourceType': source_type}, ['files'], [self.file_inventory], file_ok,
                        mismatch_details=lambda: mismatches)

        upload_source('checker.cpp', 'checker')
        # Old checkpoints can have an unresolved generator write before checker
        # selection. Reconcile that write first, without replacing its intent.
        defer_checker = self.state.get('pending') == 'gen.cpp'
        if not defer_checker:
            self.activate_checker()
        upload_source('gen.cpp', 'gen')
        if defer_checker:
            self.activate_checker()
        solutions = self.read('problem.solutions')
        if any(s.get('tag') == 'MA' and s['name'] != 'solution.cpp' for s in solutions):
            raise WorkflowError('Có lời giải chính khác; không tự đổi tag hoặc xóa lời giải đó.')
        mismatches = []
        def solution_ok():
            mismatches[:] = self.source_mismatches('solution.cpp', p['solution'], source_type, solution=True)
            return not mismatches
        self.action('solution', 'problem.saveSolution', {'name': 'solution.cpp', 'file': p['solution'],
                    'sourceType': source_type, 'tag': 'MA'}, ['solutions'], [self.solution_inventory], solution_ok,
                    mismatch_details=lambda: mismatches)
        if any(re.search(r'#\s*include\s*[<"]testlib\.h[>"]', p[part]) for part in ('checker', 'gen', 'solution')):
            resources = self.read('problem.files').get('resourceFiles', [])
            if not any(f['name'] == 'testlib.h' for f in resources):
                self.log('testlib.h không có trong resourceFiles; sẽ kiểm tra hỗ trợ thư viện qua build có verify=true.')
            else:
                self.log('Đã xác nhận resource testlib.h trên Polygon.')
        self.action('script', 'problem.saveScript', {'testset': 'tests', 'source': p['script_sinh_test']},
                    ['script', 'tests'], [lambda: self.raw('problem.script', testset='tests'),
                                         lambda: self.read('problem.tests', testset='tests', noInputs=True)],
                    lambda: text_equal(self.raw('problem.script', testset='tests'), p['script_sinh_test']))
        self.step = 'samples'
        tests = self.read('problem.tests', testset='tests', noInputs=True)
        samples = detect_sample_indices(tests, self.options.get('sample_indices'))
        for test in tests:
            index, flag = test['index'], test['index'] in samples
            def flag_ok(index=index, flag=flag):
                rows = self.read('problem.tests', testset='tests', noInputs=True)
                return any(t['index'] == index and t['useInStatements'] == flag for t in rows)
            self.action(f'sample:{index}', 'problem.saveTest', {'testset': 'tests', 'testIndex': index,
                        'testUseInStatements': flag}, ['tests'],
                        [lambda: self.read('problem.tests', testset='tests', noInputs=True)], flag_ok)
        self.state['sample_indices'] = samples
        self.state['test_count'] = len(tests)
        self.save()
        def access_ok():
            return any(a['login'] == 'codeforces' and a['accessType'] in ('READ', 'WRITE', 'OWNER')
                       for a in self.read('problem.accesses'))
        self.action('access', 'problem.setAccess', {'login': 'codeforces', 'accessType': 'READ'},
                    ['accesses'], [lambda: self.read('problem.accesses')], access_ok)

    def verify_snapshot(self):
        current = self.snapshot()
        changed = [k for k in current if current[k] != self.state['snapshot'][k]]
        if changed:
            raise WorkflowError('Xung đột dữ liệu ngoài checkpoint: ' + ', '.join(changed))

    def commit(self):
        self.step = 'commit'
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

    def package(self):
        self.step = 'package'
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
            self.state.update(pending='build', build_before_ids=[p['id'] for p in packages])
            self.save()
            result = self.write('problem.buildPackage', full=False, verify=True)
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
            matches = [p for p in rows if p['id'] == self.state['package_id']]
            if len(matches) != 1:
                raise WorkflowError('Không tìm thấy package ID đã ghi; không build thêm.')
            package = matches[0]
            if package['revision'] != revision or package['type'] != 'standard':
                raise WorkflowError('Package không thuộc revision và loại Standard đã yêu cầu.')
            self.state['package_state'] = package['state']
            self.state['package_comment'] = package.get('comment', '')
            self.save()
            if package['state'] == 'FAILED':
                raise WorkflowError('Package FAILED: ' + package.get('comment', '(Polygon không trả chi tiết)'))
            if package['state'] == 'READY':
                self.log(f'Package {package["id"]} READY.')
                return package
            if package['state'] not in ('PENDING', 'RUNNING'):
                raise WorkflowError('Trạng thái package không nhận diện: ' + str(package['state']))
            if self.clock() >= deadline:
                raise WorkflowError('Hết thời gian chờ package; resume tiếp tục poll cùng package ID.')
            self.log(f'Package {package["id"]}: {package["state"]}')
            self.sleep(min(self.options.get('poll_interval', 5), max(0, deadline - self.clock())))

    def run(self, url_resolver):
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
        access = next(a['accessType'] for a in self.read('problem.accesses') if a['login'] == 'codeforces')
        result = {'problem_id': self.state['problem_id'], 'name': self.parts['name problem'],
                  'display_name': self.parts['name'], 'statement_language': 'vietnamese',
                  'test_count': self.state['test_count'], 'sample_indices': self.state['sample_indices'],
                  'codeforces_access': access, 'revision': self.state['revision'],
                  'package_id': package['id'], 'package_state': package['state'], 'problem_url': url,
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
