import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from webui import cookie_health


def _write_cookiefile(dir_path: Path, cookies: list[tuple[str, str, str]], expires: int = 9999999999) -> Path:
    lines = ["# Netscape HTTP Cookie File"]
    for domain, name, value in cookies:
        lines.append(f"{domain}\tTRUE\t/\tTRUE\t{expires}\t{name}\t{value}")
    path = dir_path / "cookies.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class BilibiliCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cookiefile(self, cookies=None, expires=9999999999):
        if cookies is None:
            cookies = [(".bilibili.com", "SESSDATA", "abc123")]
        return _write_cookiefile(self.tmp_path, cookies, expires=expires)

    @mock.patch("webui.cookie_health.requests.Session")
    def test_logged_in_returns_ok(self, mock_session_cls) -> None:
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": {"uname": "测试用户"}}
        mock_session = mock.Mock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        health = cookie_health.check_bilibili(self._cookiefile())
        self.assertTrue(health.ok)
        self.assertIn("测试用户", health.detail)
        mock_session.headers.update.assert_called_once()
        headers = mock_session.headers.update.call_args.args[0]
        self.assertIn("Mozilla/5.0", headers["User-Agent"])
        self.assertEqual(headers["Referer"], "https://www.bilibili.com/")

    @mock.patch("webui.cookie_health.requests.Session")
    def test_not_logged_in_returns_failure(self, mock_session_cls) -> None:
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": -101, "message": "账号未登录"}
        mock_session = mock.Mock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        health = cookie_health.check_bilibili(self._cookiefile())
        self.assertFalse(health.ok)
        self.assertIn("BILIBILI_COOKIES_FROM_BROWSER", health.suggestion)

    @mock.patch("webui.cookie_health.requests.Session")
    def test_http_412_marks_invalid(self, mock_session_cls) -> None:
        mock_resp = mock.Mock()
        mock_resp.status_code = 412
        mock_session = mock.Mock()
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        health = cookie_health.check_bilibili(self._cookiefile())
        self.assertFalse(health.ok)
        self.assertIn("412", health.detail)

    @mock.patch("webui.cookie_health.requests.Session")
    def test_network_error_returns_failure(self, mock_session_cls) -> None:
        mock_session = mock.Mock()
        mock_session.get.side_effect = requests.ConnectionError("DNS resolution failed")
        mock_session_cls.return_value = mock_session

        health = cookie_health.check_bilibili(self._cookiefile())
        self.assertFalse(health.ok)
        self.assertIn("--skip-cookie-check", health.suggestion)

    def test_unparsable_cookiefile(self) -> None:
        path = self.tmp_path / "bad.txt"
        path.write_text("not a cookie file at all", encoding="utf-8")
        health = cookie_health.check_bilibili(path)
        self.assertFalse(health.ok)
        self.assertIn("无法解析", health.detail)


class DouyinCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_key_cookies_pass(self) -> None:
        cookiefile = _write_cookiefile(
            self.tmp_path,
            [(".douyin.com", "SESSSID", "abc"), (".douyin.com", "ttwid", "xyz")],
        )
        health = cookie_health.check_douyin(cookiefile)
        self.assertTrue(health.ok)

    def test_missing_key_cookies_fail(self) -> None:
        cookiefile = _write_cookiefile(
            self.tmp_path,
            [(".douyin.com", "random_cookie", "value")],
        )
        health = cookie_health.check_douyin(cookiefile)
        self.assertFalse(health.ok)
        self.assertIn("关键登录字段", health.detail)

    def test_all_expired_cookies_fail(self) -> None:
        cookiefile = _write_cookiefile(
            self.tmp_path,
            [(".douyin.com", "SESSSID", "abc")],
            expires=1,
        )
        health = cookie_health.check_douyin(cookiefile)
        self.assertFalse(health.ok)
        self.assertIn("过期", health.detail)


class PlatformDispatchTests(unittest.TestCase):
    def test_unknown_platform_skipped(self) -> None:
        health = cookie_health.check_platform("Twitter", Path("/nonexistent"))
        self.assertTrue(health.skipped)

    def test_missing_cookiefile_skipped(self) -> None:
        health = cookie_health.check_platform("Bilibili", Path("/nonexistent/path.txt"))
        self.assertTrue(health.skipped)

    def test_youtube_always_skipped(self) -> None:
        health = cookie_health.check_platform("YouTube", Path("/some/path.txt"))
        self.assertTrue(health.skipped)


if __name__ == "__main__":
    unittest.main()
