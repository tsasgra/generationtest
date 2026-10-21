import io
import unittest
from unittest.mock import Mock, patch
import zipfile

from polygon_tool.problem_url import (
    URLIdentityError, URLResolutionError, _page_has_problem_id, _url_from_dom,
    resolve_problem_url, url_from_package, validate_problem_url,
)

PROBLEM = {"id": 123, "owner": "alice", "name": "sum", "revision": 7}
URL = "https://polygon.codeforces.com/opaqueToken/alice/sum"


def package(xml):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("problem.xml", xml)
    return buffer.getvalue()


class URLTests(unittest.TestCase):
    def test_exact_server_descriptor_link(self):
        data = package(f'<problem id="123" revision="7" short-name="sum" url="{URL}"/>')
        api = Mock()
        api.call.return_value = data
        self.assertEqual(resolve_problem_url(api, PROBLEM, 88), URL)
        api.call.assert_called_once_with("problem.package", {
            "problemId": 123, "packageId": 88, "type": "standard",
        }, binary=True)

    def test_missing_url_never_invented(self):
        with self.assertRaisesRegex(URLResolutionError, "không cung cấp"):
            url_from_package(package('<problem id="123"/>'), PROBLEM)

    def test_wrong_id_revision_owner_and_name_rejected(self):
        for attrs in ('id="124"', 'revision="8"', 'short-name="other"'):
            with self.subTest(attrs=attrs), self.assertRaises(URLIdentityError):
                url_from_package(package(f'<problem {attrs} url="{URL}"/>'), PROBLEM)
        for url in (URL.replace("alice", "bob"), URL.replace("sum", "other")):
            with self.subTest(url=url), self.assertRaises(URLIdentityError):
                validate_problem_url(url, PROBLEM)

    def test_edit_api_zip_query_and_external_url_rejected(self):
        for url in (
            "https://polygon.codeforces.com/problem?problemId=123",
            "https://polygon.codeforces.com/api/problem.package",
            URL + "/problem.xml", URL + ".zip", URL + "?type=standard",
            URL + "#anything", URL.replace(".com", ".com.evil.test"),
            URL.replace("https://", "http://"), URL + "/",
            "https://alice:secret@polygon.codeforces.com/opaqueToken/alice/sum",
        ):
            with self.subTest(url=url), self.assertRaises(URLResolutionError):
                validate_problem_url(url, PROBLEM)

    def test_no_archive_files_are_extracted(self):
        with self.assertRaises(URLResolutionError):
            url_from_package(b"not a zip", PROBLEM)
        with self.assertRaisesRegex(URLResolutionError, "DTD/entity"):
            url_from_package(package('<!DOCTYPE problem [<!ENTITY x "test">]><problem/>'), PROBLEM)

    def test_dom_matches_current_page_identity_and_exact_owner_slug(self):
        self.assertTrue(_page_has_problem_id(
            "https://polygon.codeforces.com/problem?problemId=123", [], 123))
        self.assertFalse(_page_has_problem_id(
            "https://polygon.codeforces.com/problem?problemId=124", ["123"], 123))
        self.assertFalse(_page_has_problem_id("https://evil.test/?problemId=123", [], 123))
        self.assertFalse(_page_has_problem_id("https://polygon.codeforces.com/", [], 123))
        self.assertEqual(_url_from_dom(["https://example.test/", URL, URL], PROBLEM), URL)
        with self.assertRaisesRegex(URLResolutionError, "nhiều link"):
            _url_from_dom([URL, URL.replace("opaqueToken", "anotherToken")], PROBLEM)

    def test_optional_browser_only_for_missing_descriptor_url(self):
        api = Mock()
        api.call.return_value = package('<problem id="123"/>')
        with patch("polygon_tool.problem_url._browser_url", return_value=URL) as browser:
            self.assertEqual(resolve_problem_url(api, PROBLEM, 88, browser=True), URL)
            browser.assert_called_once()
        api.call.return_value = package(f'<problem id="999" url="{URL}"/>')
        with patch("polygon_tool.problem_url._browser_url") as browser:
            with self.assertRaises(URLIdentityError):
                resolve_problem_url(api, PROBLEM, 88, browser=True)
            browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
