# Phase 5 handoff — Captivate publishing

For the session with cPanel access, after Phases 1–4 are installed and a real Show has a finalized episode (audio uploaded, countdown resolved) ready to test with.

**This is the highest-risk phase to date.** Every previous phase's Python code could be checked with real unit tests against mocked dependencies. This phase's actual correctness depends on how Captivate's live API behaves — which nothing in this build session could verify, since no Captivate credentials exist here. The field names and endpoints come from Captivate's own published OpenAPI specs (not guesses), but two things are genuinely undocumented and only defensively coded — see below.

## New credentials needed

Add to the same cPanel "Setup Python App" environment variables as before:
- `CAPTIVATE_USER_ID`
- `CAPTIVATE_API_TOKEN`

These are the shared account credentials (Section 6.1 — same account across every show, reused from the existing single-show project per `CLAUDE.md`'s credential table).

## The two things to specifically watch on the very first real run

1. **Authentication response shape.** `captivate_client.py`'s `authenticate()` checks for the bearer token at the top level of the response (`{"token": ...}`) or nested (`{"user": {"token": ...}}`) — two different sources disagreed on which is real. If authentication fails with "Could not find a bearer token in the auth response: {...}", the raw response is right there in the error — check which shape it actually is.
2. **Media upload response shape.** Same defensive pattern for `upload_media()` — undocumented in both sources consulted, checks `{"id": ...}` or `{"media": {"id": ...}}`.

**Once you see a real response for either, I'd suggest telling me which shape it actually was** so I can simplify the code to that one shape instead of leaving both paths live indefinitely — belt-and-suspenders code is fine short-term but shouldn't stay that way once the real answer is known.

## What changed since Phase 4

- New: `pipeline/captivate_client.py`, `pipeline/metadata_generation.py`.
- `pipeline/anthropic_client.py`: `generate()` gained an optional `response_schema` param (structured outputs via `output_config.format` — confirmed against the current Claude API docs) and now defaults to no tools unless explicitly requested, rather than always including web search.
- `pipeline/wp_client.py`: added `get_episode()`, `get_attachment_url()`, `download_binary()`.
- `pipeline/tick.py`: the tick loop now also generates metadata and publishes to Captivate when an episode is finalized and due — see below for exactly when "due" is.
- `net-gain-studio`: `ng_finalization` gained a `finalized_at` timestamp (GMT), recorded whenever an episode transitions to `finalized` (both the natural-countdown-elapse path and the "Publish Now" REST path) — needed to correctly compute scheduled-publish timing.

## When Captivate publish actually fires

Immediately once an episode is `finalized`, if the show's publish mode is `immediate`. If `scheduled`, at the next occurrence of the show's `publish_time` (in `publish_timezone`) at or after the moment it was finalized — this correctly handles Section 8.2's own example (Pacific-afternoon recording, 7am-Eastern-next-day publish). Metadata generation happens synchronously, immediately before the Captivate call, the first time it's needed — not on any separate schedule, per the Phase 4 amendment.

## Click-through test

1. Get a real episode to `finalized` state (Phases 3–4's flow).
2. Set the show's Captivate show ID (Phase 2's screen) to the real seed value from `CLAUDE.md`: `f40bbab2-a721-4bec-9de7-aa82b5488060` for Net Gain Edtech, if that's the show under test.
3. Run `tick.py` by hand. Watch the log for metadata generation, then the Captivate publish attempt.
4. Confirm `metadata_generated` reads `done` and `GET /wp/v2/ng_episode/{id}` shows real generated values in `meta.ng_meta_captivate_title` / `ng_meta_captivate_notes` (and the AIOSEO/YouTube fields, unused until later phases but worth eyeballing for quality).
5. Confirm `captivate_published` reads `done`, and **actually check the Captivate dashboard** (or its RSS feed) for the real episode — the code re-fetches and verifies the title matches before marking success, but that doesn't replace a human looking at the real result the first time.
6. Confirm `ng_url_captivate` got populated. If it's blank, that's the "genuinely absent from the response" fallback — worth checking what Captivate's response actually contained and telling me, since a real public URL is worth having if the API provides one under a field name the code isn't checking for.
7. Test both publish modes if you can: an `immediate`-mode show should publish within one tick pass of finalizing; a `scheduled`-mode show should wait, and not publish before its computed target moment.

## Known stubs / deferred (not bugs)

- `episode_art` is omitted from every Captivate publish call for now — Phase 8 (images) hasn't been built, so there's no square artwork to attach yet. Captivate should fall back to the show's own default artwork.
- Website and YouTube publishing don't exist yet (Phases 6, 9) — this phase only consumes the Captivate-specific slice of the metadata that's now being generated for all three.
