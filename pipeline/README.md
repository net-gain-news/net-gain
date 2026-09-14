# Net Gain Studio — Python pipeline

Phases 3–9 of the Net Gain multi-tenant newscast studio build — see `../SPEC.md` and `../CLAUDE.md`. Phase 3 is the script-generation pipeline: reads a Show's config and recent history over the `net-gain-studio` plugin's REST API, calls Claude to draft today's script, writes it back, and marks the `script_generated` step. Phase 4 adds detecting an elapsed finalization countdown (Section 8.1) — the visible countdown in the WordPress admin is a reflection of server state, not its source, so `tick.py` has to resolve it correctly even if no browser is watching. Phase 5 adds metadata generation and Captivate publishing (Section 6.1), triggered the moment an episode is finalized and due — see `captivate_client.py`'s docstring for exactly which Captivate API details are confirmed vs. defensively handled. Phase 6 adds website publishing (Section 6.2) — unlike Captivate, the actual publish logic runs inside WordPress itself (`class-rest-website-publish.php` in the plugin); this side just triggers it on the same due-check and independently re-fetches the live page to verify it, rather than trusting the creation call's own response. Phase 8 adds the image pipeline (Section 7): one Gemini-generated base image per episode, an optional per-show duotone treatment, cropped and composited into each of three platform-specific frames (`image_compositing.py`), with a pre-rendered fallback if generation fails. Phase 9 adds YouTube publishing (Section 6.3) — see "Phase 9 — YouTube" below, since it's structurally different enough from the other two publish targets to warrant its own section.

## Setup

```bash
cd pipeline
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real values; never commit .env
```

On Canspace, `.env` isn't used in production — set the same variables via cPanel's "Setup Python App" tool (Spec Section 3.1), and cron invokes `venv/bin/python tick.py` directly as a CLI process, not through a web request.

## Running

```bash
python tick.py
```

Checks every Active show for a due or manually-triggered script generation, processes each independently (one show's failure never stops the others), and exits. Intended to run frequently from a single cron entry — this is the "tick loop" CLAUDE.md's architecture note describes.

## Phase 9 — YouTube

Structurally different from Captivate/website publishing in ways worth calling out explicitly:

- **Two-phase upload/verify, not one synchronous publish-and-confirm.** YouTube's real processing delay (sometimes several minutes) means `youtube_published` spans two separate tick passes over the same step: `youtube_publish_due()` returns `"upload"` or `"verify"` rather than a plain boolean, and `in_progress` always routes to `"verify"` - the cost of a race here is a duplicate *public* video, not a retried API call, so it's never re-uploaded once a video id is recorded.
- **No refresh token or OAuth client secret ever reaches this process.** `wp_client.get_youtube_access_token(show_id)` mints a short-lived (~1hr) access token server-side in WordPress each time it's needed; see `class-rest-secrets.php` in the plugin for why (SPEC Section 3.3 - these are the one genuinely per-show secret in this whole system).
- **`video_composition.py`** renders the actual "video" YouTube gets - the episode's 16:9 art held static for the audio's full duration, via `ffmpeg` (from `imageio-ffmpeg`'s bundled static binary, not a system install - Canspace is a shared cPanel host).
- **`youtube_checklist.py`** is the pre-publish checklist SPEC Section 6.3 calls for in place of a nonexistent "optimization score" - pure logic, no network, checked before any upload is attempted.
- **`youtube_client.py`** uses `google-api-python-client` rather than this project's usual hand-rolled `requests` clients - a scoped exception justified in its own docstring (resumable upload is a genuine protocol, not a simple form POST, and this project already made the identical exception for `google-genai` in Phase 8).
- A cheap safety check before every upload: the minted token's own channel is re-verified against the show's stored channel id, to guard against the worst failure mode a multi-tenant system like this one could produce - one client's episode published to another client's channel.

## Two deliberate departures from SPEC.md Section 1

`anthropic_client.py`'s docstring explains both in full: `pause_turn` is resumed per current Anthropic documentation (no synthetic "Continue" user turn — the spec's note describes a different, standard tool-continuation pattern), and thinking is `adaptive` + `effort: low` rather than `disabled`, to avoid a documented failure mode where disabled thinking on a tool-using call can make the model write a fake tool call into visible text instead of really invoking it.

## Testing

```bash
python -m unittest discover -s tests
```

Pure-logic tests only (prompt construction, HTML stripping, lookback filtering, due-date, finalization-elapse, and publish-timing computation) — no network calls, no API key needed. `test_captivate_client.py` specifically exercises the two genuinely undocumented Captivate response shapes so both are proven to parse correctly, even though neither has been checked against a real response yet; `verify_website_publish()`'s tests mock the HTTP re-fetch the same way. `test_youtube_checklist.py` covers every checklist criterion pass/fail (including synthetic Pillow-generated thumbnails); `test_youtube_client.py` covers response normalization and the retryable-vs-not HTTP error split; `test_tick.py`'s `YouTubePublishDueTests`/`ResolveYouTubeProcessingTests` cover the upload/verify due-check matrix and the verify path's stall/timeout/title-mismatch/success branches. What these tests *can't* cover: an actual live call to Claude, WordPress, Captivate, YouTube, or a real published page. See `../PHASE_3_HANDOFF.md` through `../PHASE_9_HANDOFF.md` for the real-world run checklists.

## Deliberately not built yet

- Full failure-alerting policy — `notify.py` is a minimal, honest SMTP hook, not the real subsystem from Section 9.
- Rate-limit handling at genuine multi-show concurrent scale — shows are processed sequentially within one tick for now.
- A UI path to regenerate just an episode's YouTube metadata in place once it already exists — a pre-publish checklist failure currently has no remedy short of the manual `publish_youtube` trigger, which re-checks/re-uploads but doesn't force fresh metadata generation.
