"""Response polling checks, including Chromium fixtures with no Gemini requests."""
from contextlib import redirect_stdout
import html
import io
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from gemini_tool import browser, parts
from polygon_tool.input import PARTS


def response_events(solution='int main() {}'):
    values = {part: f'Content for {part}' for part in PARTS}
    values.update({'name problem': 'fixture-task', 'name': 'Bài kiểm thử', 'note': '', 'solution': solution})
    return [event for index, part in enumerate(PARTS, 1)
            for event in ({'part': index}, {'code': values[part]})]


class PollingPage:
    url = 'https://gemini.google.com/app/fixture'

    def __init__(self, states):
        self.states = iter(states)
        self.state = None
        self.now = 0
        self.arguments = []

    def is_closed(self):
        return False

    def evaluate(self, script, arguments):
        self.arguments.append(arguments)
        self.state = next(self.states, self.state)
        return {'url': self.url, 'user': True, 'busy': False, 'error': '', **self.state}

    def wait_for_timeout(self, milliseconds):
        self.now += milliseconds / 1000


class ResponsePollingTests(unittest.TestCase):
    def wait(self, page, timeout=5):
        with patch.object(parts.time, 'monotonic', side_effect=lambda: page.now), \
                patch.object(parts, 'check_stop'), redirect_stdout(io.StringIO()):
            return parts.wait_for_parts(page, parts.DEFAULT_PROMPT, timeout)

    def test_unchanged_response_is_parsed_once(self):
        page = PollingPage([{'revision': 'a:0', 'events': response_events()},
                            {'revision': 'a:0', 'events': None}])
        with patch.object(parts, 'parts_from_events', wraps=parts.parts_from_events) as parse:
            self.assertEqual(self.wait(page)['solution'], 'int main() {}')
        self.assertEqual(parse.call_count, 1)
        self.assertGreaterEqual(page.now, 2)
        self.assertEqual(page.arguments[1]['revision'], 'a:0')

    def test_late_solution_restarts_the_quiet_window(self):
        page = PollingPage([{'revision': 'a:0', 'events': response_events('partial')},
                            *[{'revision': 'a:0', 'events': None}] * 5,
                            {'revision': 'a:1', 'events': response_events('finished solution')},
                            {'revision': 'a:1', 'events': None}])
        self.assertEqual(self.wait(page)['solution'], 'finished solution')
        self.assertGreaterEqual(page.now, 3.2)

    def test_streaming_or_missing_response_never_reuses_cached_completion(self):
        for interruption in ({'busy': True}, {'user': False}, {}):
            with self.subTest(interruption=interruption):
                page = PollingPage([{'revision': 'a:0', 'events': response_events()},
                                    {'revision': None, 'events': None, **interruption}])
                with self.assertRaisesRegex(ValueError, 'Hết'):
                    self.wait(page, timeout=3)

    def test_partial_and_duplicate_parts_are_never_accepted(self):
        for events in (response_events()[:-2], response_events() + [{'part': 10}]):
            with self.subTest(events=events[-1]):
                page = PollingPage([{'revision': 'a:0', 'events': events},
                                    {'revision': 'a:0', 'events': None}])
                with self.assertRaisesRegex(ValueError, 'Hết'):
                    self.wait(page, timeout=3)

    def test_chat_change_and_service_errors_still_stop(self):
        for state in ({'url': 'https://gemini.google.com/app/another-chat'}, {'error': 'Daily limit'}):
            with self.subTest(state=state):
                page = PollingPage([{'revision': 'a:0', 'events': response_events(), **state}])
                with self.assertRaises(ValueError):
                    self.wait(page)


class ChromiumResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        executable = shutil.which('chromium') or shutil.which('google-chrome')
        if not executable and Path(cls.playwright.chromium.executable_path).is_file():
            executable = cls.playwright.chromium.executable_path
        if not executable:
            raise unittest.SkipTest('Install Chromium to run the browser fixtures.')
        cls.browser = cls.playwright.chromium.launch(executable_path=executable, headless=True)
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        # All traffic, including the Gemini-shaped URL, is served locally.
        self.context.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<html></html>'))
        self.page = self.context.new_page()
        self.page.goto(PollingPage.url)
        events = response_events('int main() {}\n' * 3000)
        content = ''.join(f'<h3>Part {event["part"]}: section</h3>' if 'part' in event
                          else f'<pre><code>{html.escape(event["code"])}</code></pre>' for event in events)
        self.page.set_content(
            '<style>user-query,model-response,user-query-file-preview {display:block}</style>'
            f'<user-query>{parts.DEFAULT_PROMPT}'
            '<user-query-file-preview>page.png</user-query-file-preview></user-query>'
            '<button class="stop-button">Stop</button>'
            f'<model-response>{content}</model-response>'
            '<input-container><rich-textarea><div contenteditable="true"></div></rich-textarea></input-container>')
        self.page.evaluate('''() => {
            window.scrollCalls = 0;
            Element.prototype.scrollIntoView = () => { window.scrollCalls++; };
        }''')

    def snapshot(self, revision=None):
        return self.page.evaluate(parts.RESPONSE_STATE, {'prompt': parts.DEFAULT_PROMPT, 'revision': revision})

    def stop_streaming(self):
        self.page.locator('.stop-button').evaluate("el => el.remove()")

    def test_streaming_does_not_extract_code_or_scroll(self):
        for _ in range(5):
            state = self.snapshot()
            self.assertTrue(state['busy'])
            self.assertIsNone(state['events'])
        self.assertTrue(self.page.evaluate('window.__geminiPartsCache === undefined'))
        self.assertEqual(self.page.evaluate('window.scrollCalls'), 0)

    def test_cache_tracks_text_changes_and_replaced_response_roots(self):
        self.stop_streaming()
        first = self.snapshot()
        self.assertEqual(len(first['events']), 20)
        self.assertIsNone(self.snapshot(first['revision'])['events'])
        self.page.locator('pre code').last.evaluate("el => el.textContent = 'final solution'")
        changed = self.snapshot(first['revision'])
        self.assertNotEqual(first['revision'], changed['revision'])
        self.assertEqual(parts.parts_from_events(changed['events'])['solution'], 'final solution')
        self.page.locator('model-response').evaluate('el => el.replaceWith(el.cloneNode(true))')
        replaced = self.snapshot(changed['revision'])
        self.assertNotEqual(changed['revision'], replaced['revision'])
        self.assertEqual(replaced['events'], changed['events'])
        self.assertEqual(self.page.evaluate('window.scrollCalls'), 0)

    def test_unacknowledged_snapshot_can_be_fetched_again(self):
        self.stop_streaming()
        first = self.snapshot()
        self.assertEqual(self.snapshot()['events'], first['events'])

    def test_upload_confirmation_does_not_reload_the_page(self):
        self.stop_streaming()
        navigations = []
        self.page.on('framenavigated', lambda frame: navigations.append(frame.url))
        browser.verify_saved_upload(self.page, parts.DEFAULT_PROMPT, [Path('page.png')], timeout=1)
        self.assertEqual(navigations, [])


if __name__ == '__main__':
    unittest.main()
