import unittest

from webui import openai_compatible_cleanup


class AITextExtractionTests(unittest.TestCase):
    def test_extracts_reasoning_when_content_is_empty(self) -> None:
        data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning": "OK",
                    }
                }
            ]
        }

        self.assertEqual(openai_compatible_cleanup._extract_text(data), "OK")


if __name__ == "__main__":
    unittest.main()
