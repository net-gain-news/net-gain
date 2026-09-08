"""
Wraps the Claude Messages API call used for script generation.

Two deliberate departures from SPEC.md Section 1's carried-forward lessons,
based on current Anthropic API documentation (see the Phase 3 plan for the
full reasoning):

1. pause_turn (server-tool sampling-loop limit) is resumed by resending the
   conversation ending with the paused assistant turn - no synthetic
   "Continue" user turn is added. Adding one is documented as breaking the
   server's auto-resume detection.
2. thinking is set to adaptive with a low effort level, not disabled -
   disabling thinking on a tool-using call can make the model write a tool
   call into visible text instead of really invoking it, which for a
   web-search call would mean fabricated "search results". Adaptive+low
   effort avoids both that risk and the original runaway-budget problem the
   spec's "disabled" lesson was working around.
"""

import logging

import anthropic

from retry import call_with_retries

logger = logging.getLogger("net_gain.anthropic_client")

MODEL = "claude-sonnet-5"  # SPEC.md Section 1's named, production-tested choice.
MAX_TOKENS = 16000
MAX_PAUSE_RESUMES = 5

RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)

WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 5,
}


class GenerationError(RuntimeError):
    pass


def generate(client, system, user_content, tools=None):
    """
    Runs one script-generation call to completion, transparently resuming
    through any pause_turn stops. Returns the concatenated text of the final
    response. Raises GenerationError on refusal or a truncated (max_tokens)
    result - callers should not silently accept a partial script.
    """
    tools = tools if tools is not None else [WEB_SEARCH_TOOL]
    messages = [{"role": "user", "content": user_content}]

    for _ in range(MAX_PAUSE_RESUMES + 1):
        response = call_with_retries(
            lambda: client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": "low"},
                tools=tools,
                messages=messages,
            ),
            RETRYABLE_EXCEPTIONS,
        )

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise GenerationError(f"Claude refused the generation request (category: {category})")

        if response.stop_reason == "max_tokens":
            raise GenerationError(
                f"Generation hit the {MAX_TOKENS}-token cap before finishing - "
                "raise MAX_TOKENS rather than accepting a truncated script."
            )

        if response.stop_reason == "pause_turn":
            # Resume with no added user turn - see module docstring, correction 1.
            messages.append({"role": "assistant", "content": response.content})
            continue

        return "".join(block.text for block in response.content if block.type == "text")

    raise GenerationError(f"Still paused after {MAX_PAUSE_RESUMES} resumes - giving up.")
