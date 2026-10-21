"""Offline stateful contract tests; no credentials or live Polygon requests."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from polygon_tool.api import TransportError
from polygon_tool.workflow import Workflow, WorkflowError


PARTS = {
    'name problem': 'a-plus-b-test',
    'name': 'Tổng hai số',
    'lengend': r'Cho $a, b$; tính $a+b$. Giữ \\ và $\\le$ ~.',
    'input': 'Hai số nguyên a và b.',
    'output': 'In tổng hai số.',
    'note': '',
    'checker': '#include "testlib.h"\nint main() { return 0; }',
    'gen': '#include <iostream>\nint main() { std::cout << "2 3\\n"; }',
    'script_sinh_test': '<#list 1..3 as i>\ngen normal ${i} > $\n</#list>\ngen sample 1 > $',
    'solution': '#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b;}',
}
FIXTURE_URL = 'https://polygon.codeforces.com/fixtureOpaque/test-owner/a-plus-b-test'


class FakePolygon:
    """API-shaped fake with revision, write history and injected ambiguous failures."""
    def __init__(self):
        self.problem = None
        self.info = {'timeLimit': 1000, 'memoryLimit': 256, 'inputFile': 'stdin',
                     'outputFile': 'stdout', 'interactive': False, 'wellFormed': True,
                     'skipDuplicatedTestsValidation': False}
        self.statements = {}
        self.sources = {}
        self.solutions = {}
        self.script = ''
        self.tests = []
        self.checker = ''
        self.validator = ''
        self.accesses = [{'login': 'test-owner', 'accessType': 'OWNER'},
                         {'login': 'another-editor', 'accessType': 'WRITE'}]
        self.packages = []
        self.calls = []
        self.failure_after = None
        self.failure_before = None
        self.package_state = 'READY'
        self.package_comment = ''
        self.empty_build_result = False
        self.package_readiness = []
        self.recognizable_samples = True
        self.other_settings = {
            'problem.interactor': '', 'problem.extraValidators': [], 'problem.viewTags': [],
            'problem.viewGeneralDescription': '', 'problem.viewGeneralTutorial': '',
            'problem.checkerTests': [], 'problem.validatorTests': [], 'problem.materials': [],
        }
        self.tick = 0

    def writes(self, method=None):
        return [(m, p) for m, p, mutation in self.calls if mutation and (method is None or m == method)]

    def file_meta(self, name, stored):
        return {'name': name, 'sourceType': stored['sourceType'], 'length': len(stored['file'].encode('utf-8')),
                'modificationTimeSeconds': stored['mtime']}

    def call(self, method, params=None, *, mutation=False, raw=False, binary=False):
        params = dict(params or {})
        self.calls.append((method, copy.deepcopy(params), mutation))
        if self.failure_before == method:
            self.failure_before = None
            raise TransportError('simulated connection lost before operation')
        result = self.dispatch(method, params, mutation)
        if self.failure_after == method:
            self.failure_after = None
            raise TransportError('simulated response lost after operation')
        return copy.deepcopy(result)

    def dispatch(self, method, p, mutation):
        if method == 'problems.list':
            if self.problem is None:
                return []
            if p.get('id', self.problem['id']) != self.problem['id']:
                return []
            if p.get('name', self.problem['name']) != self.problem['name']:
                return []
            return [self.problem]
        if method == 'problem.create':
            assert mutation
            assert self.problem is None, 'Duplicate problem.create'
            self.problem = {'id': 17, 'name': p['name'], 'owner': 'test-owner', 'accessType': 'OWNER',
                            'revision': 1, 'workingCopyRevision': 1, 'modified': False, 'deleted': False}
            return self.problem
        assert self.problem is not None
        assert p['problemId'] == self.problem['id']
        if mutation:
            self.tick += 1
            if method not in ('problem.setAccess', 'problem.buildPackage', 'problem.commitChanges'):
                self.problem['modified'] = True
        if method in self.other_settings:
            return self.other_settings[method]
        if method == 'problem.info':
            return self.info
        if method == 'problem.updateInfo':
            self.info.update({k: v for k, v in p.items() if k != 'problemId'})
        elif method == 'problem.statements':
            return self.statements
        elif method == 'problem.saveStatement':
            self.statements.setdefault(p['lang'], {}).update({k: v for k, v in p.items() if k not in ('problemId', 'lang')})
        elif method == 'problem.files':
            return {'sourceFiles': [self.file_meta(n, s) for n, s in sorted(self.sources.items())],
                    'resourceFiles': [{'name': 'testlib.h', 'length': 123, 'modificationTimeSeconds': 1}],
                    'auxFiles': []}
        elif method == 'problem.saveFile':
            assert p['type'] == 'source'
            self.sources[p['name']] = {'file': p['file'], 'sourceType': p['sourceType'], 'mtime': self.tick}
        elif method == 'problem.viewFile':
            return self.sources[p['name']]['file']
        elif method == 'problem.solutions':
            return [{**self.file_meta(n, s), 'tag': s['tag']} for n, s in sorted(self.solutions.items())]
        elif method == 'problem.saveSolution':
            self.solutions[p['name']] = {'file': p['file'], 'sourceType': p['sourceType'], 'tag': p['tag'], 'mtime': self.tick}
        elif method == 'problem.viewSolution':
            return self.solutions[p['name']]['file']
        elif method == 'problem.script':
            return self.script
        elif method == 'problem.saveScript':
            self.script = p['source']
            self.tests = [
                {'index': 1, 'manual': False, 'scriptLine': 'gen normal 1', 'useInStatements': False},
                {'index': 2, 'manual': False, 'scriptLine': 'gen nonsample 2', 'useInStatements': True},
                {'index': 3, 'manual': False, 'scriptLine': 'gen normal 3', 'useInStatements': False},
                {'index': 4, 'manual': False, 'scriptLine': 'gen sample 1' if self.recognizable_samples else 'gen custom 1', 'useInStatements': False},
            ]
        elif method == 'problem.tests':
            return self.tests
        elif method == 'problem.saveTest':
            assert set(p) == {'problemId', 'testset', 'testIndex', 'testUseInStatements'}, 'Must update only sample flag'
            next(t for t in self.tests if t['index'] == p['testIndex'])['useInStatements'] = p['testUseInStatements']
        elif method == 'problem.checker':
            return self.checker
        elif method == 'problem.setChecker':
            assert p['checker'] in self.sources
            self.checker = p['checker']
        elif method == 'problem.validator':
            return self.validator
        elif method == 'problem.accesses':
            return self.accesses
        elif method == 'problem.setAccess':
            found = next((a for a in self.accesses if a['login'] == p['login']), None)
            if found:
                found['accessType'] = p['accessType']
            else:
                self.accesses.append({'login': p['login'], 'accessType': p['accessType']})
        elif method == 'problem.cautions':
            return {'common': [], 'statement': [], 'structure': [], 'issues': [],
                    'packageReadinessIssues': self.package_readiness,
                    'latestPackageWarnings': [], 'ai': {'disabled': True}}
        elif method == 'problem.commitChanges':
            assert self.problem['modified']
            self.problem['revision'] += 1
            self.problem['workingCopyRevision'] = self.problem['revision']
            self.problem['modified'] = False
            return {'committed': True, 'conflictOccurred': False, 'message': 'Committed'}
        elif method == 'problem.packages':
            return self.packages
        elif method == 'problem.buildPackage':
            assert p['full'] is False and p['verify'] is True
            assert not self.problem['modified']
            package = {'id': 51 + len(self.packages), 'revision': self.problem['revision'],
                       'creationTimeSeconds': self.tick, 'state': self.package_state,
                       'comment': self.package_comment, 'type': 'standard'}
            self.packages.append(package)
            return None if self.empty_build_result else package
        else:
            raise AssertionError('Unexpected API method: ' + method)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'run_state.json'
        self.parts = dict(PARTS)
        self.options = {'input_path': str(self.root / 'problem.txt'),
                        'output_dir': str(self.root / 'result'), 'poll_timeout': 0.01,
                        'poll_interval': 0.001}
        self.api = FakePolygon()
        self.logs = []

    def workflow(self, **overrides):
        return Workflow(self.api, self.state, self.parts, {**self.options, **overrides}, log=self.logs.append)

    def resolve(self, api, problem, package_id, **options):
        self.assertEqual(problem['id'], 17)
        self.assertEqual(package_id, 51)
        self.assertEqual(problem['revision'], 2)
        return FIXTURE_URL

    def saved(self):
        return json.loads(self.state.read_text(encoding='utf-8'))

    def test_end_to_end_ready_preserves_text_and_outputs_verified_metadata(self):
        result = self.workflow().run(self.resolve)
        self.assertEqual(result['problem_id'], 17)
        self.assertEqual(result['test_count'], 4)
        self.assertEqual(result['sample_indices'], [4])
        self.assertEqual(result['package_state'], 'READY')
        self.assertEqual(result['revision'], 2)
        statement = self.api.statements['vietnamese']
        self.assertEqual(statement['notes'], '')
        self.assertEqual(statement['legend'], self.parts['lengend'])
        self.assertEqual(statement['name'], 'Tổng hai số')
        self.assertEqual(self.api.sources['gen.cpp']['file'], self.parts['gen'])
        self.assertEqual(self.api.solutions['solution.cpp']['tag'], 'MA')
        self.assertNotIn('solution.cpp', self.api.sources)
        self.assertEqual(self.api.checker, 'checker.cpp')
        self.assertEqual(self.api.script, self.parts['script_sinh_test'])
        self.assertEqual([t['index'] for t in self.api.tests if t['useInStatements']], [4])
        self.assertTrue(all(not t['manual'] for t in self.api.tests))
        self.assertEqual(next(a['accessType'] for a in self.api.accesses if a['login'] == 'another-editor'), 'WRITE')
        self.assertEqual(result['codeforces_access'], 'READ')
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)
        self.assertEqual(json.loads((self.root / 'result/result.json').read_text(encoding='utf-8')), result)
        self.assertEqual((self.root / 'result/problem_url.txt').read_text(encoding='utf-8'), FIXTURE_URL + '\n')
        self.assertTrue(self.saved()['completed'])

    def test_url_failure_keeps_ready_package_and_resume_does_not_build_again(self):
        def unavailable_url(*args, **kwargs):
            raise ValueError('Không lấy được URL chính thức từ Polygon')
        with self.assertRaisesRegex(ValueError, 'URL chính thức'):
            self.workflow().run(unavailable_url)
        self.assertEqual(self.saved()['package_id'], 51)
        self.assertEqual(self.saved()['package_state'], 'READY')
        self.assertFalse(self.saved().get('completed', False))
        self.assertFalse((self.root / 'result/result.json').exists())
        self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)

    def test_external_edit_during_url_resolution_prevents_success_output(self):
        def edited_while_resolving(*args, **kwargs):
            self.api.statements['vietnamese']['name'] = 'Changed in browser'
            return FIXTURE_URL
        with self.assertRaisesRegex(WorkflowError, 'Xung đột'):
            self.workflow().run(edited_while_resolving)
        self.assertFalse(self.saved().get('completed', False))
        self.assertFalse((self.root / 'result/result.json').exists())

    def test_resume_completed_run_has_no_additional_writes(self):
        first = self.workflow().run(self.resolve)
        write_count = len(self.api.writes())
        self.assertEqual(self.workflow().run(self.resolve), first)
        self.assertEqual(len(self.api.writes()), write_count)

    def test_create_timeout_persists_intent_and_does_not_create_again(self):
        self.api.failure_after = 'problem.create'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['pending'], 'create')
        self.assertNotIn('problem_id', self.saved())
        with self.assertRaisesRegex(WorkflowError, 'không gửi lại problem.create'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes('problem.create')), 1)
        result = self.workflow(problem_id=17).run(self.resolve)
        self.assertEqual(result['problem_id'], 17)
        self.assertEqual(len(self.api.writes('problem.create')), 1)

    def test_create_timeout_with_no_server_object_is_not_retried(self):
        self.api.failure_before = 'problem.create'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        with self.assertRaisesRegex(WorkflowError, 'không gửi lại problem.create'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes('problem.create')), 1)

    def test_id_is_saved_before_following_read_failure(self):
        self.api.failure_before = 'problem.info'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['problem_id'], 17)
        self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes('problem.create')), 1)

    def test_existing_same_name_never_adopted_or_overwritten(self):
        self.api.call('problem.create', {'name': self.parts['name problem']}, mutation=True)
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'Đã có bài cùng tên'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes()), previous_count)
        self.assertFalse(self.state.exists())

    def test_applied_statement_timeout_reconciles_without_reupload(self):
        self.api.failure_after = 'problem.saveStatement'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['pending'], 'statement')
        result = self.workflow().run(self.resolve)
        self.assertEqual(result['package_state'], 'READY')
        self.assertEqual(len(self.api.writes('problem.saveStatement')), 1)

    def test_applied_commit_timeout_recovers_revision_without_recommit(self):
        self.api.failure_after = 'problem.commitChanges'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['pending'], 'commit')
        self.assertEqual(self.saved()['revision'], 1)
        self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['revision'], 2)
        self.assertEqual(len(self.api.writes('problem.commitChanges')), 1)

    def test_applied_build_timeout_finds_same_package_and_never_rebuilds(self):
        self.api.failure_after = 'problem.buildPackage'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['pending'], 'build')
        self.assertNotIn('package_id', self.saved())
        result = self.workflow().run(self.resolve)
        self.assertEqual(result['package_id'], 51)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)

    def test_unapplied_build_timeout_does_not_blindly_retry(self):
        self.api.failure_before = 'problem.buildPackage'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        with self.assertRaisesRegex(WorkflowError, 'không build lặp'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)

    def test_build_without_result_uses_package_list(self):
        self.api.empty_build_result = True
        self.assertEqual(self.workflow().run(self.resolve)['package_id'], 51)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)

    def test_failed_package_keeps_failure_and_never_emits_success(self):
        self.api.package_state = 'FAILED'
        self.api.package_comment = 'gen.cpp: compilation failed: missing testlib.h'
        with self.assertRaisesRegex(WorkflowError, 'missing testlib.h'):
            self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['package_state'], 'FAILED')
        self.assertFalse(self.saved().get('completed', False))
        self.assertFalse((self.root / 'result/result.json').exists())
        with self.assertRaisesRegex(WorkflowError, 'Package FAILED'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)

    def test_pending_package_timeout_resumes_polling_original_id(self):
        self.api.package_state = 'RUNNING'
        with self.assertRaisesRegex(WorkflowError, 'Hết thời gian chờ'):
            self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['package_id'], 51)
        self.api.packages[0]['state'] = 'READY'
        self.assertEqual(self.workflow().run(self.resolve)['package_id'], 51)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)

    def test_readiness_blocker_preserves_actual_reason(self):
        self.api.package_readiness = [{'type': 'INVALID_TEST_SCRIPT', 'message': 'gen failed at line 3'}]
        with self.assertRaisesRegex(WorkflowError, 'gen failed at line 3'):
            self.workflow().run(self.resolve)
        self.assertEqual(self.api.writes('problem.buildPackage'), [])
        self.assertEqual(self.api.writes('problem.commitChanges'), [])

    def test_revision_mismatch_stops_without_writes(self):
        self.api.failure_before = 'problem.saveStatement'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.api.problem['revision'] = self.api.problem['workingCopyRevision'] = 3
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'Revision đã thay đổi'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes()), previous_count)

    def test_external_statement_edit_stops_without_overwriting(self):
        self.api.failure_after = 'problem.saveFile'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.api.statements['vietnamese']['legend'] = 'Changed outside uploader'
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'Xung đột'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes()), previous_count)
        self.assertEqual(self.api.statements['vietnamese']['legend'], 'Changed outside uploader')

    def test_existing_stronger_codeforces_access_is_preserved(self):
        self.api.accesses.append({'login': 'codeforces', 'accessType': 'WRITE'})
        self.assertEqual(self.workflow().run(self.resolve)['codeforces_access'], 'WRITE')
        self.assertEqual(self.api.writes('problem.setAccess'), [])

    def test_explicit_sample_indices_override_generator_mode(self):
        result = self.workflow(sample_indices=[1, 3]).run(self.resolve)
        self.assertEqual(result['sample_indices'], [1, 3])
        self.assertEqual([t['index'] for t in self.api.tests if t['useInStatements']], [1, 3])

    def test_missing_sample_stops_then_explicit_indices_resume_same_problem(self):
        self.api.recognizable_samples = False
        with self.assertRaisesRegex(ValueError, 'Không xác định được sample'):
            self.workflow().run(self.resolve)
        self.assertEqual(self.saved()['problem_id'], 17)
        self.assertEqual(self.api.writes('problem.buildPackage'), [])
        result = self.workflow(sample_indices=[4]).run(self.resolve)
        self.assertEqual(result['sample_indices'], [4])
        self.assertEqual(len(self.api.writes('problem.create')), 1)
        self.assertEqual(len(self.api.writes('problem.saveScript')), 1)

    def test_changed_input_is_rejected_before_remote_calls(self):
        self.api.failure_after = 'problem.create'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.parts['solution'] = 'different solution'
        previous_count = len(self.api.calls)
        with self.assertRaisesRegex(WorkflowError, 'Nội dung input khác'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.calls), previous_count)

    def test_pending_statement_does_not_absorb_other_language_edits(self):
        self.api.failure_after = 'problem.saveStatement'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.api.statements['english'] = {'name': 'Added by another editor', 'legend': 'external'}
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'Xung đột|checkpoint'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes()), previous_count)

    def test_pending_file_does_not_absorb_new_external_file(self):
        self.api.failure_after = 'problem.saveFile'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.api.sources['extra.cpp'] = {'file': 'external code', 'sourceType': 'cpp.g++17', 'mtime': 999}
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'Xung đột|checkpoint'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes()), previous_count)

    def test_pending_commit_does_not_accept_multiple_external_revisions(self):
        self.api.failure_after = 'problem.commitChanges'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.api.problem['revision'] = self.api.problem['workingCopyRevision'] = 4
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'commit|Revision|revision'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes()), previous_count)

    def test_external_other_setting_change_is_detected_before_commit(self):
        self.api.failure_after = 'problem.saveFile'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.api.other_settings['problem.interactor'] = 'external-interactor.cpp'
        with self.assertRaisesRegex(WorkflowError, 'other_settings'):
            self.workflow().run(self.resolve)
        self.assertEqual(self.api.writes('problem.commitChanges'), [])

    def failed_run(self):
        self.api.package_state = 'FAILED'
        self.api.package_comment = 'solution.cpp compile error'
        with self.assertRaisesRegex(WorkflowError, 'Package FAILED'):
            self.workflow().run(self.resolve)

    def test_verification_results_are_not_external_content_changes(self):
        self.api.other_settings['problem.checkerTests'] = [
            {'index': 1, 'input': '2 3', 'expectedVerdict': 'OK'}]
        def resolver(*args, **kwargs):
            row = self.api.other_settings['problem.checkerTests'][0]
            row.update(runVerdict='OK', runComment='sum is correct')
            return FIXTURE_URL
        result = self.workflow().run(resolver)
        self.assertEqual(result['package_state'], 'READY')
        self.api.other_settings['problem.checkerTests'][0]['input'] = '4 5'
        with self.assertRaisesRegex(WorkflowError, 'other_settings'):
            self.workflow().run(self.resolve)

    def test_updated_input_reuses_problem_and_creates_new_revision_package(self):
        self.failed_run()
        self.parts['solution'] += '\n// corrected compilation issue'
        workflow = self.workflow()
        workflow.accept_updated_input()
        self.api.package_state = 'READY'
        result = workflow.run(lambda *args, **kwargs: FIXTURE_URL)
        self.assertEqual(result['problem_id'], 17)
        self.assertEqual(result['revision'], 3)
        self.assertEqual(result['package_id'], 52)
        self.assertEqual(result['package_state'], 'READY')
        self.assertEqual(len(self.api.writes('problem.create')), 1)
        self.assertEqual(len(self.api.writes('problem.commitChanges')), 2)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 2)
        self.assertEqual(self.api.solutions['solution.cpp']['file'], self.parts['solution'])
        self.assertEqual(self.saved()['history'][0]['package_id'], 51)

    def test_accept_unchanged_input_rejected_without_remote_writes(self):
        self.failed_run()
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'Input không đổi'):
            self.workflow().accept_updated_input()
        self.assertEqual(len(self.api.writes()), previous_count)

    def test_updated_input_rejected_if_server_changed_externally(self):
        self.failed_run()
        self.parts['solution'] += '\n// fix'
        self.api.other_settings['problem.viewTags'] = ['external-tag']
        previous_state = self.saved()
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'Xung đột'):
            self.workflow().accept_updated_input()
        self.assertEqual(self.saved(), previous_state)
        self.assertEqual(len(self.api.writes()), previous_count)

    def test_updated_input_rejected_while_write_ambiguous(self):
        self.api.failure_after = 'problem.saveStatement'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.parts['solution'] += '\n// fix'
        with self.assertRaisesRegex(WorkflowError, 'request chưa xác định'):
            self.workflow().accept_updated_input()

    def test_retry_failed_package_creates_one_new_build_same_revision(self):
        self.failed_run()
        workflow = self.workflow()
        workflow.retry_failed_package()
        self.api.package_state = 'READY'
        result = workflow.run(lambda *args, **kwargs: FIXTURE_URL)
        self.assertEqual(result['package_id'], 52)
        self.assertEqual(result['revision'], 2)
        self.assertEqual(len(self.api.writes('problem.create')), 1)
        self.assertEqual(len(self.api.writes('problem.commitChanges')), 1)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 2)
        self.assertEqual(self.saved()['history'][0]['state'], 'FAILED')

    def test_retry_package_rejects_ready(self):
        self.workflow().run(self.resolve)
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'chưa FAILED'):
            self.workflow().retry_failed_package()
        self.assertEqual(len(self.api.writes()), previous_count)

    def test_retry_package_rejects_running(self):
        self.api.package_state = 'RUNNING'
        with self.assertRaisesRegex(WorkflowError, 'Hết thời gian chờ'):
            self.workflow().run(self.resolve)
        previous_count = len(self.api.writes())
        with self.assertRaisesRegex(WorkflowError, 'chưa FAILED'):
            self.workflow().retry_failed_package()
        self.assertEqual(len(self.api.writes()), previous_count)

    def test_retry_failed_package_rechecks_server_state(self):
        self.failed_run()
        self.api.packages[0]['state'] = 'RUNNING'
        with self.assertRaisesRegex(WorkflowError, 'chưa FAILED'):
            self.workflow().retry_failed_package()
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)

    def test_package_revision_mismatch_is_rejected(self):
        self.api.failure_after = 'problem.buildPackage'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolve)
        self.api.packages[0]['revision'] = 999
        with self.assertRaisesRegex(WorkflowError, 'không build lặp'):
            self.workflow().run(self.resolve)
        self.assertEqual(len(self.api.writes('problem.buildPackage')), 1)


if __name__ == '__main__':
    unittest.main()
