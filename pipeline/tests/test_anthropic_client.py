import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anthropic_client import GenerationError, generate


def _block(type_, text=None):
    return SimpleNamespace(type=type_, text=text)


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return self.response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


class GenerateTextExtractionTests(unittest.TestCase):
    def test_ignores_narration_between_search_calls(self):
        # Confirmed live (2026-09-25): a real draft came back with the model's
        # own "I'll research X. ... Let me search for Y." narration
        # concatenated directly in front of the actual script, because every
        # text block in the response was joined regardless of position.
        response = SimpleNamespace(
            stop_reason="end_turn",
            content=[
                _block("text", "I'll research today's news."),
                _block("server_tool_use"),
                _block("web_search_tool_result"),
                _block("text", "Let me check one more angle."),
                _block("server_tool_use"),
                _block("web_search_tool_result"),
                _block("text", "Here's the actual finished script."),
            ],
        )
        client = FakeClient(response)

        result = generate(client, system="sys", user_content="go")

        self.assertEqual(result, "Here's the actual finished script.")

    def test_joins_multiple_trailing_text_blocks(self):
        response = SimpleNamespace(
            stop_reason="end_turn",
            content=[
                _block("server_tool_use"),
                _block("web_search_tool_result"),
                _block("text", "Part one. "),
                _block("text", "Part two."),
            ],
        )
        client = FakeClient(response)

        result = generate(client, system="sys", user_content="go")

        self.assertEqual(result, "Part one. Part two.")

    def test_no_tool_use_behaves_as_before(self):
        response = SimpleNamespace(
            stop_reason="end_turn",
            content=[_block("text", "Just a plain answer.")],
        )
        client = FakeClient(response)

        result = generate(client, system="sys", user_content="go", tools=[])

        self.assertEqual(result, "Just a plain answer.")

    def test_raises_when_no_text_follows_the_last_tool_call(self):
        response = SimpleNamespace(
            stop_reason="end_turn",
            content=[
                _block("text", "Narration only, no final answer."),
                _block("server_tool_use"),
                _block("web_search_tool_result"),
            ],
        )
        client = FakeClient(response)

        with self.assertRaises(GenerationError):
            generate(client, system="sys", user_content="go")


if __name__ == "__main__":
    unittest.main()
