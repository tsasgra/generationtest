"""Response polling checks, including Chromium fixtures with no Gemini requests."""
from contextlib import ExitStack, redirect_stdout
import html
import io
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gemini_tool import browser, parts
from polygon_tool.input import PARTS, parse_problem


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

    def test_missing_message_and_missing_response_are_not_reported_as_generating(self):
        for state, message in (({'user': False}, 'tin nhắn chứa prompt'),
                               ({}, 'vùng câu trả lời'),
                               ({'busy': True}, 'Stop/streaming')):
            with self.subTest(state=state):
                page = PollingPage([{'revision': None, 'events': None, **state}])
                with self.assertRaisesRegex(ValueError, message):
                    self.wait(page, timeout=1)

    def test_busy_skill_uses_one_read_per_second_without_accepting_partial_output(self):
        page = PollingPage([{'revision': None, 'events': None, 'busy': True}])
        with self.assertRaisesRegex(ValueError, 'Hết 60 giây'):
            self.wait(page, timeout=60)
        self.assertEqual(len(page.arguments), 60)
        self.assertEqual(sum(argument['inspect'] for argument in page.arguments), 4)
        self.assertFalse(any(argument['reveal'] for argument in page.arguments))

    def test_timeout_reports_unchanged_content_and_background_tab(self):
        page = PollingPage([{'revision': None, 'events': None, 'busy': True, 'diagnostic': {
            'signature': '30:123', 'characters': 30, 'code_blocks': 0,
            'visibility': 'hidden', 'focused': False, 'online': False, 'busy_source': 'Stop',
        }}])
        with self.assertRaisesRegex(ValueError, 'nội dung không đổi khoảng 30s; tab ẩn/nền') as error:
            self.wait(page, timeout=31)
        self.assertIn('30 ký tự, 0 khối code', str(error.exception))
        self.assertIn('Trình duyệt báo mất mạng', str(error.exception))
        self.assertIn(page.url, str(error.exception))


class SequentialBrowserTests(unittest.TestCase):
    def test_reuses_login_home_and_owned_tab_without_replacing_restored_chats(self):
        for initial in ('about:blank', 'https://gemini.google.com/app?hl=en',
                        'https://gemini.google.com/u/2/app', 'https://gemini.google.com/app/old-chat'):
            with self.subTest(initial=initial), tempfile.TemporaryDirectory() as directory:
                existing = SimpleNamespace(url=initial, is_closed=lambda: False)
                created = SimpleNamespace(url='about:blank', is_closed=lambda: False)
                context = SimpleNamespace(pages=[existing], new_page=Mock(return_value=created))
                seen = []

                def process(task, page, **options):
                    seen.append(page)
                    page.url = f'https://gemini.google.com/app/{task.label}'

                root = Path(directory)
                tasks = [browser.UploadTask([SimpleNamespace(upload=Path('page.png'))],
                                            root / f'problem{n}', f'problem{n}') for n in (1, 2)]
                with patch.object(browser, 'open_browser') as opened, \
                        patch.object(browser, '_process_task', side_effect=process), \
                        patch.object(browser, 'check_stop'), redirect_stdout(io.StringIO()):
                    opened.return_value.__enter__.return_value = context
                    browser.upload_tasks(tasks, profile=root / 'profile', login_timeout=1,
                                         upload_timeout=1, prompt=parts.DEFAULT_PROMPT)
                old_chat = initial.endswith('/old-chat')
                expected = created if old_chat else existing
                self.assertTrue(all(page is expected for page in seen))
                self.assertEqual(len(seen), 2)
                self.assertEqual(context.new_page.call_count, int(old_chat))
                if old_chat:
                    self.assertEqual(existing.url, initial)


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

    def snapshot(self, revision=None, **options):
        return self.page.evaluate(parts.RESPONSE_STATE, {'prompt': parts.DEFAULT_PROMPT,
                                                         'revision': revision, **options})

    def stop_streaming(self):
        self.page.locator('.stop-button').evaluate("el => el.remove()")

    def test_streaming_does_not_extract_code_or_scroll(self):
        for _ in range(5):
            state = self.snapshot(refresh=True, reveal=True)
            self.assertTrue(state['busy'])
            self.assertIsNone(state['events'])
        self.assertTrue(self.page.evaluate('window.__geminiPartsCache === undefined'))
        self.assertEqual(self.page.evaluate('window.scrollCalls'), 0)

    def test_streaming_diagnostics_track_changes_without_returning_source(self):
        first = self.snapshot(inspect=True)
        self.assertIsNone(first['events'])
        self.assertTrue(first['busy'])
        self.assertEqual(first['diagnostic']['busy_source'], 'Stop')
        self.assertEqual(first['diagnostic']['code_blocks'], 10)
        self.assertGreater(first['diagnostic']['characters'], 30000)
        self.assertLess(len(str(first)), 1000)
        self.assertNotIn('diagnostic', self.snapshot())
        self.page.locator('pre code').last.evaluate("el => el.textContent = 'int main() { return 1; }'")
        second = self.snapshot(inspect=True)
        self.assertNotEqual(second['diagnostic']['signature'], first['diagnostic']['signature'])
        self.assertIsNone(second['events'])
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

    def test_code_block_component_without_pre_is_extracted(self):
        self.stop_streaming()
        self.page.locator('pre').evaluate_all('''elements => elements.forEach(el => {
            const block = document.createElement('code-block');
            block.style.display = 'block';
            block.innerHTML = '<div>cpp <button>Copy code</button></div>';
            block.append(el.querySelector('code'));
            el.replaceWith(block);
        })''')
        result = parts.parts_from_events(self.snapshot()['events'])
        self.assertEqual(result['name problem'], 'fixture-task')
        self.assertEqual(result['solution'], 'int main() {}\n' * 3000)

    def test_part_headings_allow_line_breaks_and_optional_punctuation(self):
        self.stop_streaming()
        self.page.locator('h3').evaluate_all('''elements => elements.forEach((el, i) => {
            el.innerHTML = i % 2 ? `Part ${i + 1}` : `<b>Part ${i + 1}</b>\nsection`;
        })''')
        self.assertEqual(parts.parts_from_events(self.snapshot()['events'])['name problem'], 'fixture-task')

    def test_disabled_stop_and_busy_attachment_do_not_hide_completed_response(self):
        self.page.locator('.stop-button').evaluate("el => el.disabled = true")
        self.page.locator('model-response').evaluate('''el => {
            const image = document.createElement('div');
            image.setAttribute('aria-busy', 'true');
            image.textContent = 'Loading illustration';
            el.append(image);
        }''')
        state = self.snapshot()
        self.assertFalse(state['busy'])
        self.assertEqual(parts.parts_from_events(state['events'])['name problem'], 'fixture-task')

    def test_send_button_with_old_stop_class_does_not_block_export(self):
        self.page.locator('.stop-button').evaluate("el => el.setAttribute('aria-label', 'Send message')")
        self.assertFalse(self.snapshot()['busy'])
        for attribute in ('aria-busy', 'data-is-streaming'):
            with self.subTest(attribute=attribute):
                self.page.locator('model-response').evaluate('(el, name) => el.setAttribute(name, "true")', attribute)
                self.assertTrue(self.snapshot()['busy'])
                self.page.locator('model-response').evaluate('(el, name) => el.removeAttribute(name)', attribute)

    def test_response_with_display_contents_remains_readable(self):
        self.stop_streaming()
        self.page.add_style_tag(content='model-response {display:contents}')
        self.assertEqual(parts.parts_from_events(self.snapshot()['events'])['name problem'], 'fixture-task')

    def test_latest_prompt_is_selected_without_accepting_old_or_ambiguous_turns(self):
        self.stop_streaming()
        self.page.locator('user-query').evaluate('''el => {
            const earlier = document.createElement('user-query');
            earlier.textContent = 'Earlier unrelated question';
            el.before(earlier);
        }''')
        self.assertEqual(parts.parts_from_events(self.snapshot()['events'])['name problem'], 'fixture-task')
        self.page.locator('user-query').first.evaluate('(el, prompt) => el.textContent = prompt', parts.DEFAULT_PROMPT)
        self.assertFalse(self.snapshot()['user'])
        self.page.locator('user-query').first.evaluate("el => el.remove()")
        self.page.locator('model-response').evaluate('''el => {
            const followup = document.createElement('user-query');
            followup.textContent = 'Different followup question';
            el.after(followup);
        }''')
        self.assertFalse(self.snapshot()['user'])

    def test_refresh_rechecks_visibility_changed_outside_the_response(self):
        self.stop_streaming()
        self.page.add_style_tag(content='body.masked pre {display:none}')
        self.page.locator('body').evaluate("el => el.classList.add('masked')")
        first = self.snapshot()
        self.assertFalse(any('code' in event for event in first['events']))
        self.page.locator('body').evaluate("el => el.classList.remove('masked')")
        changed = self.snapshot(first['revision'], refresh=True)
        self.assertNotEqual(changed['revision'], first['revision'])
        self.assertEqual(parts.parts_from_events(changed['events'])['name problem'], 'fixture-task')

    def test_wait_materializes_lazy_response_once_after_streaming_stops(self):
        self.stop_streaming()
        self.page.locator('pre code').last.evaluate("el => el.textContent = ''")
        self.page.evaluate('''() => {
            Element.prototype.scrollIntoView = () => {
                window.scrollCalls++;
                setTimeout(() => {
                    document.querySelector('pre:last-child code').textContent = 'finished after rendering';
                }, 20);
            };
        }''')
        with patch.object(parts, 'check_stop'), redirect_stdout(io.StringIO()):
            result = parts.wait_for_parts(self.page, parts.DEFAULT_PROMPT, timeout=8)
        self.assertEqual(result['solution'], 'finished after rendering')
        self.assertEqual(self.page.evaluate('window.scrollCalls'), 1)

    def test_completed_task_writes_ten_files_with_reused_send_button(self):
        self.page.locator('.stop-button').evaluate("el => el.setAttribute('aria-label', 'Send message')")
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            # Start at the submitted-message boundary; extraction, confirmation
            # and writing all ten UTF-8 files run against the real browser DOM.
            for name in ('new_chat', 'pause_after_action', 'choose_files', 'wait_for_upload', 'send_prompt'):
                stack.enter_context(patch.object(browser, name))
            stack.enter_context(patch.object(parts, 'check_stop'))
            stack.enter_context(patch.object(browser, 'check_stop'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            output = Path(directory) / 'problem1'
            task = browser.UploadTask([SimpleNamespace(upload=Path('page.png'))], output, 'problem1')
            browser._process_task(task, self.page, login_timeout=1, upload_timeout=1,
                                  prompt=parts.DEFAULT_PROMPT, keep_images=True,
                                  attach_only=False, response_timeout=5)
            self.assertEqual(len(list(output.glob('*.txt'))), 10)
            self.assertEqual(parse_problem(output)['solution'], 'int main() {}\n' * 3000)
            self.assertEqual(self.page.evaluate('window.scrollCalls'), 0)

    def test_upload_confirmation_does_not_reload_the_page(self):
        self.stop_streaming()
        navigations = []
        self.page.on('framenavigated', lambda frame: navigations.append(frame.url))
        browser.verify_saved_upload(self.page, parts.DEFAULT_PROMPT, [Path('page.png')], timeout=1)
        self.assertEqual(navigations, [])


if __name__ == '__main__':
    unittest.main()
