import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anthropic_client import WEB_SEARCH_TOOL, GenerationError, _without_dangling_tool_calls, generate


def _block(type_, text=None):
    return SimpleNamespace(type=type_, text=text)


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = 0
        self.last_kwargs = None

    def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
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


class RequestConfigTests(unittest.TestCase):
    def test_thinking_is_adaptive_not_disabled(self):
        # Re-enabled 2026-09-29 (explicit human-operator request) after being
        # disabled since Phase 3 - see the module docstring for why.
        response = SimpleNamespace(stop_reason="end_turn", content=[_block("text", "ok")])
        client = FakeClient(response)

        generate(client, system="sys", user_content="go")

        self.assertEqual(client.messages.last_kwargs["thinking"], {"type": "adaptive"})

    def test_web_search_max_uses_is_20(self):
        # Raised from 14 -> 20 on 2026-09-29 (explicit human-operator request),
        # after a live draft showed the model citing search-budget pressure.
        self.assertEqual(WEB_SEARCH_TOOL["max_uses"], 20)


class LogUsageTests(unittest.TestCase):
    def test_does_not_raise_when_usage_is_missing(self):
        # A real generation must never fail because logging itself broke -
        # usage() shape can vary by SDK version/response.
        response = SimpleNamespace(stop_reason="end_turn", content=[_block("text", "ok")])
        client = FakeClient(response)

        result = generate(client, system="sys", user_content="go")

        self.assertEqual(result, "ok")

    def test_logs_usage_fields_including_web_search_requests(self):
        usage = SimpleNamespace(
            input_tokens=1234,
            output_tokens=567,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            server_tool_use=SimpleNamespace(web_search_requests=3),
        )
        response = SimpleNamespace(stop_reason="end_turn", content=[_block("text", "ok")], usage=usage)
        client = FakeClient(response)

        with self.assertLogs("net_gain.anthropic_client", level="INFO") as captured:
            generate(client, system="sys", user_content="go")

        logged = "\n".join(captured.output)
        self.assertIn("input=1234", logged)
        self.assertIn("output=567", logged)
        self.assertIn("cache_read=100", logged)
        self.assertIn("cache_write=50", logged)
        self.assertIn("web_search_requests=3", logged)
        self.assertIn("generate(script_generation)", logged)

    def test_purpose_is_other_when_tools_explicitly_empty(self):
        usage = SimpleNamespace(
            input_tokens=1, output_tokens=1, cache_read_input_tokens=0,
            cache_creation_input_tokens=0, server_tool_use=None,
        )
        response = SimpleNamespace(stop_reason="end_turn", content=[_block("text", "ok")], usage=usage)
        client = FakeClient(response)

        with self.assertLogs("net_gain.anthropic_client", level="INFO") as captured:
            generate(client, system="sys", user_content="go", tools=[])

        self.assertIn("generate(other)", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()


class PausedTurnTests(unittest.TestCase):
    """Production failure 2026-10-05/06: a pause_turn response ended in a web_search call with no result block,
    and resuming with it in the history was rejected with a 400."""

    @staticmethod
    def _call(id_):
        return SimpleNamespace(type="server_tool_use", id=id_, name="web_search")

    @staticmethod
    def _result(id_):
        return SimpleNamespace(type="web_search_tool_result", tool_use_id=id_)

    def test_removes_only_the_unanswered_call(self):
        content = [_block("text", "Searching."), self._call("a"), self._result("a"), self._call("b")]
        kept = _without_dangling_tool_calls(content)
        self.assertEqual([getattr(b, "id", None) or getattr(b, "tool_use_id", None) for b in kept[1:]], ["a", "a"])
        self.assertEqual(len(kept), 3)

    def test_leaves_complete_turns_and_idless_blocks_alone(self):
        content = [_block("server_tool_use"), _block("web_search_tool_result"), self._call("a"), self._result("a")]
        self.assertEqual(len(_without_dangling_tool_calls(content)), 4)

    def test_a_paused_turn_is_resumed_without_the_dangling_call(self):
        paused = SimpleNamespace(stop_reason="pause_turn", content=[
            SimpleNamespace(type="thinking", text=None), _block("text", "Looking."), self._call("a"), self._result("a"), self._call("b"),
        ])
        final = SimpleNamespace(stop_reason="end_turn", content=[_block("text", "The finished script.")])
        sent = []

        class Messages:
            def create(self, **kwargs):
                sent.append([dict(m) for m in kwargs["messages"]])
                return paused if len(sent) == 1 else final

        client = SimpleNamespace(messages=Messages())
        self.assertEqual(generate(client, system="s", user_content="go"), "The finished script.")
        assistant = sent[1][1]
        self.assertEqual(assistant["role"], "assistant")
        ids = [getattr(b, "id", None) for b in assistant["content"] if b.type == "server_tool_use"]
        self.assertEqual(ids, ["a"])                                   # "b" had no result and was dropped
        self.assertEqual(sent[1][2], {"role": "user", "content": "Continue."})
