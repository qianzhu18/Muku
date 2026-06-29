import json
import unittest
from unittest import mock

import requests

from webui import openrouter_backends


class OpenRouterRequestErrorTests(unittest.TestCase):
    def test_402_error_includes_openrouter_message_and_does_not_retry(self) -> None:
        response = requests.Response()
        response.status_code = 402
        response.url = "https://openrouter.ai/api/v1/chat/completions"
        response._content = json.dumps(
            {"error": {"message": "This request requires at least $0.50 in balance for audio", "code": 402}}
        ).encode("utf-8")
        response.headers["Content-Type"] = "application/json"

        with mock.patch.object(openrouter_backends, "OPENROUTER_API_KEY", "sk-test"), mock.patch.object(
            openrouter_backends, "OPENROUTER_MAX_RETRIES", 6
        ), mock.patch.object(
            openrouter_backends.requests, "post", return_value=response
        ) as post, mock.patch.object(
            openrouter_backends.time, "sleep"
        ) as sleep:
            with self.assertRaises(RuntimeError) as cm:
                openrouter_backends._post_chat({"model": "openai/gpt-audio-mini", "messages": []})

        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()
        self.assertIn("402 Client Error", str(cm.exception))
        self.assertIn("requires at least $0.50 in balance for audio", str(cm.exception))

    def test_429_retries(self) -> None:
        rate_limited = requests.Response()
        rate_limited.status_code = 429
        rate_limited.url = "https://openrouter.ai/api/v1/chat/completions"
        rate_limited._content = b'{"error":{"message":"rate limited","code":429}}'
        rate_limited.headers["Content-Type"] = "application/json"

        ok = mock.Mock()
        ok.raise_for_status.return_value = None
        ok.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with mock.patch.object(openrouter_backends, "OPENROUTER_API_KEY", "sk-test"), mock.patch.object(
            openrouter_backends, "OPENROUTER_MAX_RETRIES", 2
        ), mock.patch.object(
            openrouter_backends.requests, "post", side_effect=[rate_limited, ok]
        ) as post, mock.patch.object(
            openrouter_backends.time, "sleep"
        ) as sleep:
            data = openrouter_backends._post_chat({"model": "openai/gpt-audio-mini", "messages": []})

        self.assertEqual(data["choices"][0]["message"]["content"], "ok")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
