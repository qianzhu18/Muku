import unittest
from unittest import mock

from webui import http_utils


class HttpUtilsProxyTests(unittest.TestCase):
    def test_no_proxy_returns_none(self) -> None:
        env = {k: v for k, v in http_utils.os.environ.items()
               if k not in {"OPENROUTER_PROXY", "HTTPS_PROXY", "HTTP_PROXY",
                            "https_proxy", "http_proxy"}}
        with mock.patch.dict(http_utils.os.environ, env, clear=True):
            self.assertIsNone(http_utils.get_proxies())

    def test_explicit_openrouter_proxy(self) -> None:
        env = {"OPENROUTER_PROXY": "http://127.0.0.1:7897"}
        with mock.patch.dict(http_utils.os.environ, env, clear=True):
            proxies = http_utils.get_proxies()
        self.assertEqual(proxies, {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"})

    def test_falls_back_to_https_proxy_env(self) -> None:
        env = {"HTTPS_PROXY": "http://127.0.0.1:7897", "HTTP_PROXY": ""}
        with mock.patch.dict(http_utils.os.environ, env, clear=True):
            proxies = http_utils.get_proxies()
        self.assertEqual(proxies["https"], "http://127.0.0.1:7897")


class HttpUtilsSslTests(unittest.TestCase):
    def test_default_enables_verify(self) -> None:
        env = {k: v for k, v in http_utils.os.environ.items()
               if k != "OPENROUTER_INSECURE_SKIP_VERIFY"}
        with mock.patch.dict(http_utils.os.environ, env, clear=True):
            self.assertTrue(http_utils.get_ssl_verify())

    def test_insecure_flag_disables_verify(self) -> None:
        with mock.patch.dict(http_utils.os.environ, {"OPENROUTER_INSECURE_SKIP_VERIFY": "true"}, clear=True):
            self.assertFalse(http_utils.get_ssl_verify())


class HttpUtilsRequestKwargsTests(unittest.TestCase):
    def test_empty_when_unconfigured(self) -> None:
        env = {k: v for k, v in http_utils.os.environ.items()
               if k not in {"OPENROUTER_PROXY", "HTTPS_PROXY", "HTTP_PROXY",
                            "OPENROUTER_INSECURE_SKIP_VERIFY"}}
        with mock.patch.dict(http_utils.os.environ, env, clear=True):
            self.assertEqual(http_utils.request_kwargs(), {})

    def test_includes_proxies_and_verify(self) -> None:
        env = {"OPENROUTER_PROXY": "http://127.0.0.1:7897", "OPENROUTER_INSECURE_SKIP_VERIFY": "true"}
        with mock.patch.dict(http_utils.os.environ, env, clear=True):
            kwargs = http_utils.request_kwargs()
        self.assertEqual(kwargs["proxies"]["https"], "http://127.0.0.1:7897")
        self.assertFalse(kwargs["verify"])


if __name__ == "__main__":
    unittest.main()
