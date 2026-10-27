"""Exercise the real Polygon workflow against an API that forbids content read-back."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from polygon_tool.api import APIError, TransportError
from polygon_tool.input import PARTS
from polygon_tool.workflow import Workflow, WorkflowError, atomic_json, digest


class PolygonFixture:
    def __init__(self):
        self.calls = []
        self.problem = None
        self.tests = []
        self.packages = []
        self.fail_once = None
        self.lose_once = None
        self.package_state = 'READY'
        self.package_issues = []
        self.info = {'timeLimit': 1000, 'memoryLimit': 256, 'inputFile': '', 'outputFile': ''}

    def call(self, method, params=None, *, mutation=False, raw=False):
        params = dict(params or {})
        self.calls.append((method, deepcopy(params), mutation))
        if method == self.fail_once:
            self.fail_once = None
            raise APIError('Polygon rejected this write', method=method)
        if not mutation:
            if method == 'problems.list':
                return [deepcopy(self.problem)] if self.problem else []
            if method == 'problem.info':
                # Defaults may be read once before content is uploaded.
                if any(write and name != 'problem.create' for name, _, write in self.calls):
                    raise AssertionError('Must not read info back after writing')
                return dict(self.info)
            if method == 'problem.tests':
                return deepcopy(self.tests)
            if method == 'problem.cautions':
                return {'packageReadinessIssues': deepcopy(self.package_issues)}
            if method == 'problem.packages':
                return deepcopy(self.packages)
            raise AssertionError(f'Unexpected content verification request: {method}')

        result = None
        if method == 'problem.create':
            self.problem = {'id': 123, 'name': params['name'], 'owner': 'tester',
                            'revision': 1, 'workingCopyRevision': 1,
                            'modified': False, 'accessType': 'OWNER'}
            result = deepcopy(self.problem)
        elif method == 'problem.updateInfo':
            self.info.update({key: value for key, value in params.items() if key != 'problemId'})
            self.problem['modified'] = True
        elif method == 'problem.saveScript':
            self.tests = [{'index': 1, 'manual': False, 'scriptLine': 'gen sample', 'useInStatements': False},
                          {'index': 2, 'manual': False, 'scriptLine': 'gen random', 'useInStatements': False}]
            self.problem['modified'] = True
        elif method == 'problem.saveTest':
            next(t for t in self.tests if t['index'] == params['testIndex'])['useInStatements'] = params['testUseInStatements']
            self.problem['modified'] = True
        elif method in ('problem.saveStatement', 'problem.saveFile', 'problem.setChecker',
                        'problem.saveSolution', 'problem.setAccess'):
            self.problem['modified'] = True
        elif method == 'problem.commitChanges':
            self.problem['revision'] += 1
            self.problem['workingCopyRevision'] = self.problem['revision']
            self.problem['modified'] = False
            result = {'committed': True, 'conflictOccurred': False}
        elif method == 'problem.buildPackage':
            result = {'id': 200 + len(self.packages), 'revision': self.problem['revision'],
                      'type': 'standard', 'state': self.package_state, 'comment': 'fixture'}
            self.packages.append(dict(result))
        else:
            raise AssertionError(f'Unexpected write: {method}')
        if method == self.lose_once:
            self.lose_once = None
            raise TransportError('Response lost after server accepted the request', method=method)
        return result


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'checkpoint.json'
        self.parts = {part: f'Content for {part}' for part in PARTS}
        self.parts.update({'name problem': 'fixture-task', 'name': 'Bài kiểm thử', 'note': ''})
        self.options = {'input_path': str(self.root / 'problem'), 'output_dir': str(self.root / 'result'),
                        'timeLimit': 2345, 'sample_indices': None, 'poll_timeout': 1}
        self.api = PolygonFixture()
        self.resolver = lambda *args, **kwargs: 'https://polygon.codeforces.com/p/tester/fixture-task'

    def workflow(self):
        return Workflow(self.api, self.path, self.parts, self.options, log=lambda message: None)

    def writes(self):
        return Counter(name for name, _, write in self.api.calls if write)

    def test_upload_uses_acknowledgements_without_content_readback(self):
        result = self.workflow().run(self.resolver)
        self.assertEqual(result['package_state'], 'READY')
        self.assertEqual(result['sample_indices'], [1])
        self.assertEqual(result['info']['timeLimit'], 2345)
        self.assertEqual(result['info']['memoryLimit'], 256)
        self.assertEqual(result['codeforces_access'], 'READ')
        reads = Counter(name for name, _, write in self.api.calls if not write)
        self.assertEqual(reads['problem.info'], 1)
        self.assertEqual(reads['problem.tests'], 1)
        self.assertEqual(self.writes(), Counter({
            'problem.create': 1, 'problem.updateInfo': 1, 'problem.saveStatement': 1,
            'problem.saveFile': 2, 'problem.setChecker': 1, 'problem.saveSolution': 1,
            'problem.saveScript': 1, 'problem.saveTest': 2, 'problem.setAccess': 1,
            'problem.commitChanges': 1, 'problem.buildPackage': 1}))
        state = json.loads(self.path.read_text())
        self.assertNotIn('snapshot', state)
        self.assertTrue(state['completed'])
        self.assertEqual(state['upload_receipts']['statement'], digest(self.workflow().upload_requests()['statement']))
        final_writes = [(name, params) for name, params, write in self.api.calls if write][-3:]
        self.assertEqual([name for name, _ in final_writes],
                         ['problem.setAccess', 'problem.commitChanges', 'problem.buildPackage'])
        self.assertEqual(final_writes[0][1], {'problemId': 123, 'login': 'codeforces', 'accessType': 'READ'})
        self.assertEqual(result['revision'], 2)
        self.assertEqual(self.api.packages[0]['revision'], result['revision'])

    def test_access_failure_blocks_commit_and_package_until_resume(self):
        self.api.fail_once = 'problem.setAccess'
        with self.assertRaises(APIError):
            self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.commitChanges'], 0)
        self.assertEqual(self.writes()['problem.buildPackage'], 0)
        self.assertEqual(json.loads(self.path.read_text())['pending'], 'access')
        self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.setAccess'], 2)
        self.assertEqual(self.writes()['problem.commitChanges'], 1)
        self.assertEqual(self.writes()['problem.buildPackage'], 1)

    def test_commit_failure_blocks_package_until_resume(self):
        self.api.fail_once = 'problem.commitChanges'
        with self.assertRaises(APIError):
            self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.setAccess'], 1)
        self.assertEqual(self.writes()['problem.buildPackage'], 0)
        self.assertEqual(json.loads(self.path.read_text())['pending'], 'commit')
        self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.setAccess'], 1)
        self.assertEqual(self.writes()['problem.commitChanges'], 2)
        self.assertEqual(self.writes()['problem.buildPackage'], 1)

    def test_package_issue_does_not_prevent_committing_uploaded_changes(self):
        self.api.package_issues = [{'type': 'FIXTURE_PACKAGE_ISSUE', 'message': 'Package not ready'}]
        with self.assertRaisesRegex(WorkflowError, 'Polygon chặn package'):
            self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.setAccess'], 1)
        self.assertEqual(self.writes()['problem.commitChanges'], 1)
        self.assertEqual(self.writes()['problem.buildPackage'], 0)
        self.assertTrue(json.loads(self.path.read_text())['committed'])
        self.assertFalse(self.api.problem['modified'])
        self.api.package_issues.clear()
        self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.commitChanges'], 1)
        self.assertEqual(self.writes()['problem.buildPackage'], 1)

    def test_api_error_stops_and_resume_retries_only_unacknowledged_steps(self):
        self.api.fail_once = 'problem.setChecker'
        with self.assertRaises(APIError):
            self.workflow().run(self.resolver)
        state = json.loads(self.path.read_text())
        self.assertEqual(state['pending'], 'checker')
        self.assertNotIn('checker', state['upload_receipts'])
        self.assertEqual(self.writes()['problem.buildPackage'], 0)
        self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.setChecker'], 2)
        self.assertEqual(self.writes()['problem.saveStatement'], 1)
        self.assertEqual(self.writes()['problem.saveFile'], 2)
        self.assertEqual(self.writes()['problem.create'], 1)

    def test_lost_statement_response_is_replayed_without_readback(self):
        self.api.lose_once = 'problem.saveStatement'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolver)
        self.assertEqual(json.loads(self.path.read_text())['pending'], 'statement')
        self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.saveStatement'], 2)
        self.assertEqual(self.writes()['problem.updateInfo'], 1)
        self.assertEqual(self.writes()['problem.create'], 1)

    def test_lost_commit_and_build_responses_do_not_repeat_mutations(self):
        self.api.lose_once = 'problem.commitChanges'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolver)
        self.api.lose_once = 'problem.buildPackage'
        with self.assertRaises(TransportError):
            self.workflow().run(self.resolver)
        self.assertEqual(self.workflow().run(self.resolver)['package_state'], 'READY')
        self.assertEqual(self.writes()['problem.commitChanges'], 1)
        self.assertEqual(self.writes()['problem.buildPackage'], 1)
        self.assertEqual(self.writes()['problem.saveStatement'], 1)

    def test_failed_package_is_not_reported_as_complete(self):
        self.api.package_state = 'FAILED'
        with self.assertRaisesRegex(WorkflowError, 'Package FAILED'):
            self.workflow().run(self.resolver)
        self.assertFalse(json.loads(self.path.read_text()).get('completed', False))
        self.assertFalse((self.root / 'result/result.json').exists())

    def test_updated_script_reapplies_sample_flags_without_content_readback(self):
        self.workflow().run(self.resolver)
        self.parts['script_sinh_test'] = 'New generator script'
        workflow = self.workflow()
        workflow.accept_updated_input()
        workflow.run(self.resolver)
        self.assertTrue(self.api.tests[0]['useInStatements'])
        self.assertEqual(self.writes()['problem.saveScript'], 2)
        self.assertEqual(self.writes()['problem.saveTest'], 4)
        self.assertEqual(self.writes()['problem.saveStatement'], 1)
        self.assertEqual(self.writes()['problem.buildPackage'], 2)

    def test_legacy_pending_upload_migrates_without_fetching_remote_snapshot(self):
        self.api.fail_once = 'problem.setChecker'
        with self.assertRaises(APIError):
            self.workflow().run(self.resolver)
        saved = json.loads(self.path.read_text())
        requests = self.workflow().upload_requests()
        saved['snapshot'] = {'info': saved.pop('info'),
            'statements': {'vietnamese': {k: v for k, v in requests['statement'][1].items()
                                         if k not in ('lang', 'encoding')}},
            'files': {}, 'solutions': {}, 'tests': [], 'accesses': [], 'checker': None}
        saved['upload_receipts'] = {'checker.cpp': saved['upload_receipts']['checker.cpp']}
        atomic_json(self.path, saved)
        self.workflow().run(self.resolver)
        self.assertEqual(self.writes()['problem.saveStatement'], 1)
        self.assertEqual(self.writes()['problem.updateInfo'], 1)
        self.assertNotIn('snapshot', json.loads(self.path.read_text()))

    def test_wrong_problem_identity_still_blocks_writes(self):
        workflow = self.workflow()
        workflow.create_or_recover()
        self.api.problem['owner'] = 'someone-else'
        with self.assertRaisesRegex(WorkflowError, 'danh tính'):
            workflow.run(self.resolver)
        self.assertEqual(self.writes(), Counter({'problem.create': 1}))


if __name__ == '__main__':
    unittest.main()
