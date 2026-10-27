"""Resumable Polygon uploads using API acknowledgements, without content read-back."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

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


class Workflow:
    def __init__(self, api, state_path: Path, parts: dict, options: dict,
                 *, log: Callable[[str], None] | None = None, sleep=time.sleep,
                 monotonic=time.monotonic):
        self.api, self.path, self.parts, self.options = api, Path(state_path), parts, options
        self.log = log or (lambda message: print(message, file=sys.stderr))
        self.sleep, self.clock = sleep, monotonic
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.step = 'preflight'
        self.migrate_upload_receipts()

    def upload_requests(self):
        source_type = self.options.get('source_type', 'cpp.g++17')
        p = self.parts
        return {
            'info': ('problem.updateInfo', {k: self.options[k]
                     for k in ('timeLimit', 'memoryLimit', 'inputFile', 'outputFile')
                     if self.options.get(k) is not None}),
            'statement': ('problem.saveStatement', {'lang': 'vietnamese', 'encoding': 'UTF-8',
                          'name': p['name'], 'legend': p['lengend'], 'input': p['input'],
                          'output': p['output'], 'notes': p['note']}),
            'checker.cpp': ('problem.saveFile', {'type': 'source', 'name': 'checker.cpp',
                            'file': self.parts['checker'], 'sourceType': source_type}),
            'checker': ('problem.setChecker', {'checker': 'checker.cpp'}),
            'gen.cpp': ('problem.saveFile', {'type': 'source', 'name': 'gen.cpp',
                        'file': self.parts['gen'], 'sourceType': source_type}),
            'solution': ('problem.saveSolution', {'name': 'solution.cpp', 'file': self.parts['solution'],
                         'sourceType': source_type, 'tag': 'MA'}),
            'script': ('problem.saveScript', {'testset': 'tests', 'source': self.parts['script_sinh_test']}),
            'access': ('problem.setAccess', {'login': 'codeforces', 'accessType': 'READ'}),
        }

    def migrate_upload_receipts(self):
        """Convert local snapshots from older versions without querying Polygon."""
        if not self.state or 'snapshot' not in self.state:
            return
        snapshot = self.state.pop('snapshot')
        self.state.setdefault('info', snapshot.get('info', {}))
        access = next((a['accessType'] for a in snapshot.get('accesses', [])
                       if a['login'] == 'codeforces'), None)
        if access:
            self.state.setdefault('codeforces_access', access)
        if digest(self.parts) != self.state.get('input_digest'):
            return
        requests = self.upload_requests()
        statement = snapshot.get('statements', {}).get('vietnamese', {})
        completed = {
            'info': all(snapshot.get('info', {}).get(k) == v for k, v in requests['info'][1].items()),
            'statement': all(isinstance(statement.get(k), str) and text_equal(statement[k], v)
                             for k, v in requests['statement'][1].items() if k not in ('lang', 'encoding')),
            'checker.cpp': 'source:checker.cpp' in snapshot.get('files', {}),
            'checker': snapshot.get('checker') == 'checker.cpp',
            'gen.cpp': 'source:gen.cpp' in snapshot.get('files', {}),
            'solution': 'solution.cpp' in snapshot.get('solutions', {}),
            'script': bool(snapshot.get('script')),
            'access': access in ('READ', 'WRITE', 'OWNER'),
        }
        receipts = self.state.setdefault('upload_receipts', {})
        for label, done in completed.items():
            if done and self.state.get('pending') != label:
                receipts.setdefault(label, digest(requests[label]))
        for test in snapshot.get('tests', []):
            label = f"sample:{test['index']}"
            if self.state.get('pending') != label and type(test.get('useInStatements')) is bool:
                receipts.setdefault(label, digest(('problem.saveTest', {
                    'testset': 'tests', 'testIndex': test['index'],
                    'testUseInStatements': test['useInStatements']})))

    def save(self):
        atomic_json(self.path, self.state)

    def accept_updated_input(self):
        """Explicit correction of the same problem, after checking server ownership."""
        self.step = 'update-input'
        if not self.state.get('problem_id'):
            raise WorkflowError('Phải xác định problem ID trước khi đổi input.')
        if self.state.get('pending'):
            raise WorkflowError('Còn request chưa xác định kết quả; resume xử lý request đó trước khi đổi input.')
        self.check_revision()  # Also checks slug/owner against the actual object.
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
                          'create_before_ids': [r['id'] for r in existing], 'pending': 'create',
                          'upload_receipts': {}}
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

    def initialize_info(self):
        if 'info' not in self.state:
            self.check_revision()
            # Read defaults once, before uploading. Later reports use these
            # values plus settings acknowledged by problem.updateInfo.
            self.state['info'] = self.read('problem.info')
            self.save()

    def action(self, label, method, params):
        """Record successful writes; resume replays only unacknowledged setters."""
        self.step = label
        receipt = digest((method, params))
        receipts = self.state.setdefault('upload_receipts', {})
        pending = self.state.get('pending')
        if receipts.get(label) == receipt and pending != label:
            if label == 'access':
                self.log('Manage Access: quyền codeforces đã có ghi nhận trong checkpoint.')
            return False
        if pending and pending != label:
            raise WorkflowError(f'Chưa hoàn tất {label}; đang chờ xử lý {pending}.')
        self.check_revision()
        self.log('Manage Access: cấp quyền READ cho codeforces.' if label == 'access' else f'Đang lưu: {label}')
        self.state['pending'] = label
        self.save()
        # API errors leave the intent intact. Named saves can be retried;
        # create, commit and build keep their separate recovery paths.
        self.write(method, **params)
        if label == 'script':
            # Saving a new script can recreate tests and reset Example flags.
            for key in list(receipts):
                if key.startswith('sample:'):
                    receipts.pop(key)
        receipts[label] = receipt
        self.state['pending'] = None
        self.save()
        return True

    def upload(self):
        requests = self.upload_requests()
        if requests['info'][1]:
            self.action('info', *requests['info'])
            self.state['info'].update(requests['info'][1])
        self.log('Giới hạn/tệp áp dụng: ' + json.dumps(self.state['info'], ensure_ascii=False))
        self.action('statement', *requests['statement'])
        self.action('checker.cpp', *requests['checker.cpp'])
        # Older checkpoints may have a pending generator upload before the
        # checker selection was introduced. Finish that pending save first.
        defer_checker = self.state.get('pending') == 'gen.cpp'
        if not defer_checker:
            self.action('checker', *requests['checker'])
        self.action('gen.cpp', *requests['gen.cpp'])
        if defer_checker:
            self.action('checker', *requests['checker'])
        self.action('solution', *requests['solution'])
        self.action('script', *requests['script'])
        self.step = 'samples'
        # This list supplies indices after FreeMarker expansion; it is not a
        # comparison against uploaded content and is read only once per run.
        tests = self.read('problem.tests', testset='tests', noInputs=True)
        samples = detect_sample_indices(tests, self.options.get('sample_indices'))
        for test in tests:
            index, flag = test['index'], test['index'] in samples
            self.action(f'sample:{index}', 'problem.saveTest', {'testset': 'tests',
                        'testIndex': index, 'testUseInStatements': flag})
        self.state['sample_indices'] = samples
        self.state['test_count'] = len(tests)
        self.save()
        if self.action('access', *requests['access']):
            self.state['codeforces_access'] = requests['access'][1]['accessType']
            self.save()
            self.log('Manage Access: API đã xác nhận codeforces có quyền READ.')

    def commit(self):
        self.step = 'commit'
        meta = self.metadata()
        if self.state.get('pending') == 'commit':
            if meta['revision'] == self.state['revision'] + 1 and not meta['modified']:
                self.state.update(revision=meta['revision'], committed=True, pending=None)
                self.save()
                self.log(f'Commit Changes: đã khôi phục commit revision {meta["revision"]}.')
                return
            if meta['revision'] != self.state['revision'] or not meta['modified']:
                raise WorkflowError('Không xác định được commit bị gián đoạn; kiểm tra revision trên Polygon.')
        else:
            self.check_revision()
        if self.state.get('committed'):
            if meta['modified']:
                raise WorkflowError('Có thay đổi chưa commit sau checkpoint đã commit.')
            self.log(f'Commit Changes: revision {meta["revision"]} đã commit theo checkpoint.')
            return
        # Package readiness is checked in package(), after committing. A
        # packaging issue must not prevent saving the uploaded working copy.
        self.state['pending'] = 'commit'
        self.save()
        self.log('Commit Changes: đang lưu thay đổi vào repository Polygon.')
        result = self.write('problem.commitChanges', minorChanges=True, message='Upload with polygon_upload')
        if not isinstance(result, dict) or result.get('conflictOccurred') or not result.get('committed'):
            raise WorkflowError('Commit không được xác nhận: ' + str(result))
        meta = self.metadata()
        if meta['modified'] or meta['revision'] != self.state['revision'] + 1:
            raise WorkflowError('Commit chưa tạo revision mới sạch; giữ checkpoint.')
        self.state.update(revision=meta['revision'], committed=True, pending=None)
        self.save()
        self.log(f'Commit Changes: đã commit revision {meta["revision"]}.')

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
            self.log(f'Packages: tạo package Standard từ revision {revision} đã commit.')
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
        self.initialize_info()
        # A pending commit may already have increased revision; reconcile before upload checks.
        if self.state.get('pending') == 'commit':
            self.commit()
        if not self.state.get('committed'):
            self.upload()
            self.commit()
        else:
            self.check_revision()
        package = self.package()
        self.step = 'url'
        problem = self.metadata()
        problem['revision'] = self.state['revision']
        url = url_resolver(self.api, problem, package['id'], browser=self.options.get('browser', False),
                           profile=Path(self.options.get('browser_profile', '.polygon-browser')),
                           timeout=self.options.get('browser_timeout', 300))
        self.check_revision()
        access = self.state.get('codeforces_access', 'READ')
        result = {'problem_id': self.state['problem_id'], 'name': self.parts['name problem'],
                  'display_name': self.parts['name'], 'statement_language': 'vietnamese',
                  'test_count': self.state['test_count'], 'sample_indices': self.state['sample_indices'],
                  'codeforces_access': access, 'revision': self.state['revision'],
                  'package_id': package['id'], 'package_state': package['state'], 'problem_url': url,
                  'info': self.state['info']}
        output = Path(self.options.get('output_dir', '.'))
        atomic_json(output / 'result.json', result)
        output.mkdir(parents=True, exist_ok=True)
        tmp = output / 'problem_url.txt.tmp'
        tmp.write_text(url + '\n', encoding='utf-8')
        os.replace(tmp, output / 'problem_url.txt')
        self.state.update(completed=True, result=result, pending=None)
        self.save()
        return result
