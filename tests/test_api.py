import io
import json
import unittest
import urllib.error
import urllib.parse
from unittest.mock import Mock, patch

from polygon_tool.api import APIError, PolygonAPI, TransportError


class Response(io.BytesIO):
    def __init__(self, value, status=200):
        if not isinstance(value, bytes):
            value = json.dumps(value, ensure_ascii=False).encode("utf-8")
        super().__init__(value)
        self.status = status


def http_error(code, body=b""):
    return urllib.error.HTTPError("https://polygon.codeforces.com/api/problems.list",
                                  code, "error", {}, io.BytesIO(body))


class APITransportTests(unittest.TestCase):
    def setUp(self):
        self.api = PolygonAPI("test-key", "test-secret", interval=0, retries=2)
        self.api._opener = Mock()
        self.sleep = patch("polygon_tool.api.time.sleep").start()
        self.addCleanup(patch.stopall)

    def test_signature_covers_exact_source_before_encoding(self):
        content = "Tiếng Việt \\alpha $ ~ & +\r\n"
        self.api._opener.open.return_value = Response({"status": "OK"})
        with patch("polygon_tool.api.time.time", return_value=1700000000), \
                patch("polygon_tool.api.secrets.token_hex", return_value="abcdef"):
            self.api.call("problem.saveFile", {
                "name": "gen.cpp", "file": content, "type": "source"}, mutation=True)
        req = self.api._opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertNotIn("?", req.full_url)
        params = urllib.parse.parse_qs(req.data.decode("ascii"), keep_blank_values=True)
        self.assertEqual(params["file"], [content])
        self.assertEqual(params["apiSig"], [
            "abcdef72beb2566e61669f37556d53e2d7d3ec18f5cdbb5f8995f7db06f53105c0a8dd"
            "e07f6fd8f78e70542dd85d15c0ead3caa33e426dc7a8d04e8de9b73c680c350b"])

    def test_empty_notes_and_boolean_serialization(self):
        self.api._opener.open.return_value = Response({"status": "OK", "result": 9})
        self.assertEqual(self.api.call("problem.saveStatement", {
            "notes": "", "showInReview": False, "optional": None}, mutation=True), 9)
        req = self.api._opener.open.call_args.args[0]
        params = urllib.parse.parse_qs(req.data.decode(), keep_blank_values=True)
        self.assertEqual(params["notes"], [""])
        self.assertEqual(params["showInReview"], ["false"])
        self.assertNotIn("optional", params)

    def test_http_200_failed_is_error_and_not_retried(self):
        self.api._opener.open.return_value = Response({"status": "FAILED", "comment": "Bad API key"})
        with self.assertRaisesRegex(APIError, "Bad API key"):
            self.api.call("problems.list")
        self.assertEqual(self.api._opener.open.call_count, 1)

    def test_raw_endpoint_detects_api_failure(self):
        self.api._opener.open.return_value = Response({"status": "FAILED", "comment": "No such file"})
        with self.assertRaisesRegex(APIError, "No such file"):
            self.api.call("problem.viewFile", {"name": "x.cpp"}, raw=True)

    def test_raw_response_preserves_utf8_crlf_and_special_characters(self):
        original = "// tiếng Việt\r\n\\alpha $ ~ &\r\n"
        self.api._opener.open.return_value = Response(original.encode())
        self.assertEqual(self.api.call("problem.viewSolution", raw=True), original)

    def test_binary_package_returns_exact_bytes(self):
        blob = b"PK\x03\x04\x00\xff\x80"
        self.api._opener.open.return_value = Response(blob)
        self.assertEqual(self.api.call("problem.package", binary=True), blob)

    def test_binary_endpoint_detects_api_failure(self):
        self.api._opener.open.return_value = Response({"status": "FAILED", "comment": "No package"})
        with self.assertRaises(APIError):
            self.api.call("problem.package", binary=True)

    def test_read_retries_transient_network_failure(self):
        self.api._opener.open.side_effect = [urllib.error.URLError("offline"),
                                           Response({"status": "OK", "result": [1]})]
        self.assertEqual(self.api.call("problems.list"), [1])
        self.assertEqual(self.api._opener.open.call_count, 2)

    def test_read_retries_429_and_503(self):
        self.api._opener.open.side_effect = [http_error(429), http_error(503),
                                           Response({"status": "OK", "result": []})]
        self.assertEqual(self.api.call("problems.list"), [])
        self.assertEqual(self.api._opener.open.call_count, 3)

    def test_authentication_failure_is_not_retried(self):
        self.api._opener.open.side_effect = http_error(403, b'{"status":"FAILED","comment":"Access denied"}')
        with self.assertRaisesRegex(APIError, "Access denied"):
            self.api.call("problems.list")
        self.assertEqual(self.api._opener.open.call_count, 1)

    def test_retries_are_bounded(self):
        self.api._opener.open.side_effect = TimeoutError("no response")
        with self.assertRaises(TransportError) as caught:
            self.api.call("problems.list")
        self.assertFalse(caught.exception.ambiguous)
        self.assertEqual(self.api._opener.open.call_count, 3)

    def test_mutation_timeout_is_never_retried_and_hides_network_detail(self):
        self.api._opener.open.side_effect = TimeoutError("apiSig=abc test-key test-secret")
        with self.assertRaises(TransportError) as caught:
            self.api.call("problem.create", {"name": "abc"}, mutation=True)
        self.assertTrue(caught.exception.ambiguous)
        self.assertEqual(self.api._opener.open.call_count, 1)
        self.assertNotIn("test-key", str(caught.exception))
        self.assertNotIn("test-secret", str(caught.exception))
        self.assertNotIn("apiSig", str(caught.exception))

    def test_mutation_http_500_is_ambiguous_not_retried(self):
        self.api._opener.open.side_effect = http_error(500)
        with self.assertRaises(TransportError) as caught:
            self.api.call("problem.buildPackage", {"full": False}, mutation=True)
        self.assertTrue(caught.exception.ambiguous)
        self.assertEqual(self.api._opener.open.call_count, 1)

    def test_invalid_json_after_write_is_ambiguous(self):
        self.api._opener.open.return_value = Response(b"<html>Gateway error</html>")
        with self.assertRaises(TransportError) as caught:
            self.api.call("problem.commitChanges", mutation=True)
        self.assertTrue(caught.exception.ambiguous)

    def test_error_redacts_server_echo_of_credentials_and_signed_url(self):
        self.api._opener.open.return_value = Response({"status": "FAILED", "comment":
            "test-key test-secret https://polygon.codeforces.com/api/problems.list?apiKey=test-key&apiSig=xyz"})
        with self.assertRaises(APIError) as caught:
            self.api.call("problems.list")
        error = str(caught.exception)
        self.assertNotIn("test-key", error)
        self.assertNotIn("test-secret", error)
        self.assertNotIn("xyz", error)

    def test_reserved_auth_and_invalid_method_fail_before_network(self):
        for method, params in [("../../outside", {}), ("problems.list", {"apiKey": "other"})]:
            with self.subTest(method=method), self.assertRaises(ValueError):
                self.api.call(method, params)
        self.api._opener.open.assert_not_called()

    def test_conflicting_output_modes_fail_before_network(self):
        with self.assertRaises(ValueError):
            self.api.call("problem.package", raw=True, binary=True)
        self.api._opener.open.assert_not_called()

    def test_plain_exception_constructor_for_workflow(self):
        self.assertTrue(TransportError("lost response").ambiguous)
        self.assertFalse(APIError("rejected").ambiguous)


if __name__ == "__main__":
    unittest.main()
