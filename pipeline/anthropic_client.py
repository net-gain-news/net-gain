"""
Wraps the Claude Messages API call used for script generation.

The pause/truncation continuation strategy below (a synthetic "Continue."
user turn on resume) matches the prototype's generate_script.py, not current
API documentation - kept regardless of the thinking setting below, since
it's the resume mechanism itself (this model has no assistant-prefill
support), not something thinking changes.

thinking was disabled from Phase 3 (2026-09-12) through 2026-09-29: a live
run on 2026-09-10, at the original 8-search web_search budget, reproduced a
failure mode where the model exhausted that budget mid-turn and, rather
than truly pausing, wrote out text explaining it couldn't continue. Re-
enabled 2026-09-29 (adaptive) alongside raising max_uses 14->20, on an
explicit human-operator request to test whether it improves story-selection
judgment - a materially larger search budget than the one that triggered
the original failure, but not proven not to recur. Watch generate()'s usage
logging (added the same day) for a repeat: a response that stops for a
reason other than a clean end_turn/tool completion, especially paired with
a web_search_requests count at or near max_uses, is the signature to look
for.
"""

import logging

import anthropic

from retry import call_with_retries
from text_rules import apply_text_rules

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
    # Reverted from "web_search_20260209" (2026-09-12): that was Phase 3's
    # unverified guess from documentation, never actually confirmed against a
    # live response. Every real run using it failed to get search results
    # starting from the very first search attempt in the turn ("No results
    # returned"), which the model then misread as its own search budget being
    # exhausted - a guess on its part, not a real diagnosis. This value is the
    # prototype's proven one (generate_script.py), confirmed across real,
    # successful production runs, not a guess.
    "type": "web_search_20250305",
    "name": "web_search",
    # Was 8 (the prototype's proven value) until 2026-09-25, then 14. Raised
    # to 20 on 2026-09-29 (explicit human-operator request, alongside
    # re-enabling thinking) after a live draft's own leaked search narration
    # (see the text-extraction fix below) showed the model citing "given my
    # remaining budget" right before settling for a weaker, staler lead story
    # over a fresher one a human found independently. Each search is a flat
    # $10/1000 fee regardless of model or token usage - watch
    # web_search_requests in the new usage logging below to see how much of
    # this budget episodes are actually using.
    "max_uses": 20,
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


def _without_dangling_tool_calls(content):
    """
    Drop any server-side tool call (web_search) that has no result block in the same content.

    Diagnosed 2026-10-07 from the production log: every script run whose first response stopped with
    pause_turn then died on the continuation request with
    "messages.1: `web_search` tool use with id srvtoolu_... was found without a corresponding
    `web_search_tool_result` block" (400), on 10/5 once and on 10/6 three times in a row - each failed run
    having already paid for ~17-19 searches (about a million input tokens). A pause can land between the
    model issuing a search and the result arriving, so the paused turn ends in a call with no result. We
    then send that turn back followed by a "Continue." user message, and the API (rightly) refuses an
    unanswered tool call that is followed by another user turn. Removing the unanswered call lets the model
    simply issue that search again on resume.
    """
    content = list(content)
    answered = {getattr(b, "tool_use_id", None) for b in content if str(getattr(b, "type", "")).endswith("_tool_result")}
    kept = []
    for block in content:
        block_id = getattr(block, "id", None)
        if getattr(block, "type", "") == "server_tool_use" and block_id is not None and block_id not in answered:
            logger.warning("Dropping unanswered server tool call %s (%s) from the paused turn before resuming.",
                           block_id, getattr(block, "name", "?"))
            continue
        kept.append(block)
    return kept


def _log_usage(purpose, attempt, response):
    """
    Added 2026-09-29 alongside re-enabling thinking and raising max_uses, on
    an explicit human-operator request for real per-episode cost data rather
    than the estimates used to make that decision. Logs one line per API
    call (a multi-attempt generation via the Continue-turn loop above logs
    once per attempt, each with that call's own usage - sum across attempts
    with the same purpose/timestamp to get a whole generation's real cost).

    Every field is read defensively (getattr with a 0 default) - usage
    object shape can vary by SDK version and by what the call actually used
    (e.g. no cache fields if caching wasn't in play), and a logging call must
    never be what makes a real generation fail.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        logger.warning("generate(%s) attempt %d: no usage data on the response.", purpose, attempt)
        return

    server_tool_use = getattr(usage, "server_tool_use", None)
    web_search_requests = getattr(server_tool_use, "web_search_requests", 0) if server_tool_use else 0

    logger.info(
        "generate(%s) attempt %d usage: input=%d output=%d cache_read=%d cache_write=%d "
        "web_search_requests=%d stop_reason=%s",
        purpose,
        attempt,
        getattr(usage, "input_tokens", 0),
        getattr(usage, "output_tokens", 0),
        getattr(usage, "cache_read_input_tokens", 0),
        getattr(usage, "cache_creation_input_tokens", 0),
        web_search_requests,
        response.stop_reason,
    )


def generate(client, system, user_content, tools=None, response_schema=None, effort="low"):
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

    effort separately controls how much overall effort the model puts into
    the response, independent of thinking (adaptive below, as of 2026-09-29 -
    see the module docstring) - defaults to "low" for the repackaging-style
    calls (metadata, image prompts), overridden to "high" for script
    generation itself per an explicit human-operator request (2026-09-12)
    for genuine research/writing quality, not just the fastest passable
    answer.
    """
    tools = tools if tools is not None else [WEB_SEARCH_TOOL]
    messages = [{"role": "user", "content": user_content}]

    output_config = {"effort": effort}
    if response_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": response_schema}

    # No dedicated "purpose" parameter - script_generation.py is the only
    # caller that leaves tools at its web_search default (see the docstring
    # above); every other caller (metadata, image prompts) explicitly passes
    # tools=[]. Inferring from that is enough to tell the two apart in logs
    # without changing every call site's signature.
    purpose = "script_generation" if any(t.get("name") == "web_search" for t in tools) else "other"

    response = None
    for attempt in range(1, MAX_CONTINUATIONS + 1):
        response = call_with_retries(
            lambda: client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                thinking={"type": "adaptive"},
                output_config=output_config,
                tools=tools,
                messages=messages,
            ),
            RETRYABLE_EXCEPTIONS,
        )
        _log_usage(purpose, attempt, response)

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise GenerationError(f"Claude refused the generation request (category: {category})")

        if response.stop_reason not in ("pause_turn", "max_tokens"):
            break

        trimmed = _without_trailing_thinking(_without_dangling_tool_calls(response.content))
        if not trimmed:
            break  # Nothing usable to continue from - fall through and report.

        messages.append({"role": "assistant", "content": trimmed})
        messages.append({"role": "user", "content": "Continue."})

    # Confirmed live (2026-09-25): with web_search, Anthropic runs the whole
    # search loop server-side within one response - so response.content can
    # hold several text blocks interleaved with search calls ("I'll research
    # X.", then a search, "Let me check Y.", another search, ...) before the
    # actual final answer. Naively joining every text block concatenated that
    # narration straight into the saved script ("...build today's script.Here's
    # the latest from Net Gain Edtech..."), confirmed on a live draft. Only
    # text blocks after the last non-text (tool-use/tool-result) block are the
    # real answer - anything earlier is commentary between searches.
    last_non_text_idx = -1
    for i, block in enumerate(response.content):
        if block.type != "text":
            last_non_text_idx = i
    text = "".join(
        block.text for block in response.content[last_non_text_idx + 1:] if block.type == "text"
    )
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
    # House text rules (text_rules.py): K-12 always uses the non-breaking hyphen, whatever the model wrote.
    return apply_text_rules(text)
