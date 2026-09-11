"""
Wraps the Claude Messages API call used for script generation.

thinking and the pause/truncation continuation strategy below match the
prototype's generate_script.py exactly, not current API documentation -
Phase 3 originally chose differently based on documentation alone (adaptive
thinking instead of disabled, and no synthetic "Continue" user turn on
resume), and a live run on 2026-09-10 reproduced precisely the failure mode
the prototype's approach exists to avoid: the model exhausted its web_search
budget mid-turn and, rather than truly pausing, wrote out text explaining
that it couldn't continue and asking to be sent another message. Documented
API behavior and observed live behavior disagreed; the proven prototype
wins.
"""

import logging

import anthropic

from retry import call_with_retries

logger = logging.getLogger("net_gain.anthropic_client")

MODEL = "claude-sonnet-5"  # SPEC.md Section 1's named, production-tested choice.
MAX_TOKENS = 16000
MAX_CONTINUATIONS = 5

RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    # anthropic.APITimeoutError is a subclass of APIConnectionError (confirmed
    # via the SDK's own class MRO, 2026-09-11) - a timeout on the explicit
    # client-level timeout set in tick.py already retries through this entry,
    # no separate one needed.
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)

WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    # Matches the prototype's proven value (generate_script.py) - not a guess.
    "max_uses": 8,
}


class GenerationError(RuntimeError):
    pass


def _without_trailing_thinking(content):
    """The API rejects an assistant message whose final block is `thinking`
    (happens when a turn is interrupted mid-thought). Trim any such trailing
    blocks before feeding a response back in as conversation history - ported
    verbatim from the prototype's generate_script.py."""
    content = list(content)
    while content and content[-1].type in ("thinking", "redacted_thinking"):
        content.pop()
    return content


def generate(client, system, user_content, tools=None, response_schema=None):
    """
    Runs one generation call to completion, transparently resuming through
    any pause_turn or max_tokens stop by appending the paused assistant turn
    plus a plain "Continue." user turn (the prototype's proven mechanism -
    this model has no assistant-prefill support, so a turn can't be resumed
    by ending on an assistant message alone). Returns the concatenated text
    of the final response. Raises GenerationError on refusal, or if nothing
    usable comes out after MAX_CONTINUATIONS attempts - callers should not
    silently accept a partial or empty result.

    tools defaults to web search (script generation's use case) - pass
    tools=[] explicitly for calls that shouldn't search (e.g. metadata
    generation, which only repackages an already-written script).

    response_schema, if given, is a JSON Schema object enforced via
    output_config.format (structured outputs) - the returned text is then
    guaranteed valid JSON matching it, rather than relying on a prompt
    instruction alone.
    """
    tools = tools if tools is not None else [WEB_SEARCH_TOOL]
    messages = [{"role": "user", "content": user_content}]

    output_config = {"effort": "low"}
    if response_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": response_schema}

    response = None
    for attempt in range(1, MAX_CONTINUATIONS + 1):
        response = call_with_retries(
            lambda: client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                thinking={"type": "disabled"},
                output_config=output_config,
                tools=tools,
                messages=messages,
            ),
            RETRYABLE_EXCEPTIONS,
        )

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise GenerationError(f"Claude refused the generation request (category: {category})")

        if response.stop_reason not in ("pause_turn", "max_tokens"):
            break

        trimmed = _without_trailing_thinking(response.content)
        if not trimmed:
            break  # Nothing usable to continue from - fall through and report.

        messages.append({"role": "assistant", "content": trimmed})
        messages.append({"role": "user", "content": "Continue."})

    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        block_types = [block.type for block in response.content]
        logger.warning(
            "No text block after %d attempt(s). stop_reason=%s, content block types=%s",
            attempt,
            response.stop_reason,
            block_types,
        )
        raise GenerationError(
            f"Generation finished (stop_reason={response.stop_reason}) but produced no "
            "usable text content - refusing to treat an empty result as a real script."
        )
    return text
