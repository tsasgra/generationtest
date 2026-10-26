"""Authenticated Polygon HTTP transport using the Python standard library.

Protocol: https://codeforces.github.io/polygon-misc/API#authorization
Text uploads are the documented ``file`` form parameter. The signature covers
its exact UTF-8 text before URL encoding, just like every other parameter.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import math
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping

BASE_URL = "https://polygon.codeforces.com/api/"


class APIError(RuntimeError):
    """A rejected request; message is safe to show to the user."""

    def __init__(self, message: str, *, method: str | None = None,
                 status_code: int | None = None):
        super().__init__(message)
        self.method = method
        self.status_code = status_code
        self.ambiguous = False


class TransportError(APIError):
    """The response cannot establish whether a write reached the server."""

    def __init__(self, message: str, *, method: str | None = None,
                 status_code: int | None = None, ambiguous: bool = True):
        super().__init__(message, method=method, status_code=status_code)
        self.ambiguous = ambiguous


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirected authenticated POST must not forward credentials.
        return None


class PolygonAPI:
    def __init__(self, key: str, secret: str, timeout: float = 60,
                 retries: int = 3, interval: float = 1.0, *, request_gate=None):
        if not isinstance(key, str) or not key or not isinstance(secret, str) or not secret:
            raise ValueError("Cần POLYGON_API_KEY và POLYGON_API_SECRET.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout phải lớn hơn 0.")
        if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
            raise ValueError("retries phải là số nguyên không âm.")
        if not math.isfinite(interval) or interval < 0:
            raise ValueError("interval phải không âm.")
        self._key = key
        self._secret = secret
        self.timeout = timeout
        self.retries = retries
        self.interval = interval
        self._request_gate = request_gate
        self._last_request = None
        self._opener = urllib.request.build_opener(_NoRedirect())

    def redact(self, message: object) -> str:
        """Remove credentials and signatures, including encoded echoes."""
        text = str(message)
        for value in (self._key, self._secret):
            for encoded in (value, urllib.parse.quote(value, safe=""),
                            urllib.parse.quote_plus(value)):
                text = text.replace(encoded, "[REDACTED]")
        text = re.sub(r"(?i)(apiSig|apiKey|secret)(\s*[=:]\s*)[^\s&\"'<>]+",
                      r"\1\2[REDACTED]", text)
        text = re.sub(r"(?i)apiSig%3D[^\s&\"'<>]+", "apiSig=[REDACTED]", text)
        text = re.sub(r"(?i)https?://[^\s\"'<>]*\?[^\s\"'<>]*",
                      "[URL REDACTED]", text)
        return text

    @staticmethod
    def _value(value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return value
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float) and math.isfinite(value):
            return str(value)
        raise ValueError("Tham số Polygon phải là chuỗi, số hoặc bool.")

    def _signed_parameters(self, method: str, params: Mapping | None) -> dict[str, str]:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*", method):
            raise ValueError("Tên phương thức Polygon không hợp lệ.")
        values: dict[str, str] = {}
        for key, value in (params or {}).items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", key):
                raise ValueError("Tên tham số Polygon không hợp lệ.")
            if key in {"apiKey", "apiSig", "time"}:
                raise ValueError("Không tự truyền tham số xác thực Polygon.")
            if value is not None:
                values[key] = self._value(value)
        values["apiKey"] = self._key
        values["time"] = str(int(time.time()))
        prefix = secrets.token_hex(3)
        canonical = "&".join(f"{k}={v}" for k, v in sorted(values.items()))
        payload = f"{prefix}/{method}?{canonical}#{self._secret}"
        values["apiSig"] = prefix + hashlib.sha512(payload.encode("utf-8")).hexdigest()
        return values

    def _throttle(self) -> None:
        if self._request_gate is not None:
            self._request_gate()
            return
        if self._last_request is not None:
            delay = self.interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
        self._last_request = time.monotonic()

    def call(self, method: str, params: Mapping | None = None, *,
             mutation: bool = False, raw: bool = False, binary: bool = False):
        """Return JSON result, exact UTF-8 text, or bytes.

        Only read calls retry network errors, HTTP 429 and HTTP 5xx. Mutations
        are attempted once: the workflow must reconcile them before resuming.
        HTTP 200 with status FAILED is always an error, including raw endpoints.
        """
        if raw and binary:
            raise ValueError("raw và binary không thể cùng được bật.")
        attempts = 1 if mutation else self.retries + 1
        for attempt in range(attempts):
            self._throttle()
            signed = self._signed_parameters(method, params)
            request = urllib.request.Request(
                BASE_URL + method,
                data=urllib.parse.urlencode(signed, encoding="utf-8").encode("ascii"),
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                         "Accept": "*/*" if raw or binary else "application/json",
                         "User-Agent": "polygon-upload/1.0"},
                method="POST",
            )
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    status = response.status
                    body = response.read()
            except urllib.error.HTTPError as exc:
                status = exc.code
                try:
                    body = exc.read()
                except (OSError, EOFError, http.client.HTTPException):
                    body = b""
                finally:
                    exc.close()
            except (urllib.error.URLError, OSError, EOFError, http.client.HTTPException) as exc:
                if attempt + 1 < attempts:
                    time.sleep(min(2 ** attempt, 30))
                    continue
                # Do not include urllib exception text: it may contain request
                # objects, signed parameters or other sensitive data.
                raise TransportError(
                    f"{method}: lỗi mạng hoặc hết thời gian chờ ({type(exc).__name__}).",
                    method=method, ambiguous=mutation,
                ) from None

            envelope = None
            try:
                candidate = json.loads(body)
                if isinstance(candidate, dict) and candidate.get("status") in ("OK", "FAILED"):
                    envelope = candidate
            except (ValueError, UnicodeError):
                pass

            if not (200 <= status < 300):
                transient = status == 429 or 500 <= status < 600
                if transient and attempt + 1 < attempts:
                    time.sleep(min(2 ** attempt, 30))
                    continue
                comment = envelope.get("comment") if envelope else None
                message = self.redact(str(comment or f"HTTP {status}; không có thông báo lỗi API hợp lệ.").replace(signed["apiSig"], "[REDACTED]"))
                error_class = TransportError if status >= 500 else APIError
                kwargs = {"method": method, "status_code": status}
                if error_class is TransportError:
                    kwargs["ambiguous"] = mutation
                raise error_class(f"{method}: {message}", **kwargs)

            if envelope and envelope["status"] == "FAILED":
                message = self.redact(str(envelope.get("comment", "Polygon trả status FAILED.")).replace(signed["apiSig"], "[REDACTED]"))
                raise APIError(f"{method}: {message}", method=method, status_code=status)
            if binary:
                return body
            if raw:
                try:
                    return body.decode("utf-8")
                except UnicodeError:
                    raise TransportError(f"{method}: phản hồi không phải UTF-8 hợp lệ.",
                                         method=method, ambiguous=mutation) from None
            if envelope is None:
                raise TransportError(f"{method}: phản hồi không phải JSON Polygon hợp lệ.",
                                     method=method, ambiguous=mutation)
            return envelope.get("result")
        raise AssertionError("unreachable")
