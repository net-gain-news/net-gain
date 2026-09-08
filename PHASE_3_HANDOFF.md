# Phase 3 handoff — Script generation pipeline

For the session with cPanel access to Canspace, after Phases 1–2 (`PHASE_1_HANDOFF.md`, `PHASE_2_HANDOFF.md`) are installed and verified on `netgain.news`, and a real Show exists there (e.g. Net Gain Edtech, per `CLAUDE.md`'s seed data).

This is the first Python code in the project — nothing here has run against the real site or a real Anthropic key yet. This build session verified only pure logic with everything mocked (see `pipeline/README.md`).

## Install on Canspace

1. cPanel → Setup Python App → create an app pointed at the `pipeline/` directory, pick a Python version (3.9+; the code uses stdlib `zoneinfo`, available since 3.9).
2. Use the app's provided `pip install` (not a bare `pip`) to install `pipeline/requirements.txt` into its venv.
3. Set environment variables via the Setup Python App UI (not a `.env` file in production): `ANTHROPIC_API_KEY`, `WP_BASE_URL`, `WP_SERVICE_USERNAME`, `WP_SERVICE_APP_PASSWORD` — the last two are the Application Password credential created in the Phase 1 handoff for the `ng_service`-role user. SMTP vars are optional (see below).
4. **Do not wire the cron job yet** — run `tick.py` by hand first (below) before anything runs unattended.

## First real run (by hand, before any cron)

1. In wp-admin, make sure at least one Show is `Active`, has a Vertical with real guidelines seeded, has `recording_days`/`target_time`/`recording_timezone` set, and has a primary talent assigned (Phase 2's screen).
2. Either wait until the show's actual target time passes, or trigger it manually: `POST /wp-json/net-gain/v1/shows/{id}/actions` with `{"action":"generate_script"}` (as an admin — see Phase 1's handoff for the exact call shape).
3. Run `venv/bin/python tick.py` from the `pipeline/` directory by hand and watch the log output.
4. Confirm: a new `ng_episode` post now exists for today's date under that show; `GET /wp-json/wp/v2/ng_episode/{id}` shows `meta.ng_script_draft` populated with real generated text (not empty, not an error message); the dashboard step reads `script_generated: done` (via `GET /wp-json/wp/v2/ng_episode/{id}` → `meta.ng_step_status.script_generated`); the manual-trigger action from step 2 now shows `status: done` on the show.
5. Run `tick.py` **again** immediately. It should log "Script already generated ... skipping" and do nothing — this is the idempotency guarantee from Section 8.3; if it generates a second script instead, something is wrong with the step-status check and should be looked at before any cron job is wired up.
6. Check whether the generated script actually used web search (rather than making something up) — the easiest check is whether the content references specific, real, checkable current stories. If it reads generic/vague, that's worth a closer look at the `anthropic_client.py` tool wiring before trusting this in production.

## Once the manual run looks right

Add the single Canspace cron entry (Section 3.1) invoking the venv's Python binary directly on `tick.py` — every few minutes is reasonable, not an exact spec requirement. Confirm the cron environment's `PATH` and timezone the same way the original single-show build did (Section 1's lessons: minimal `PATH` in cron, never assume UTC — a disposable cron job that just logs `date` is the fastest sanity check).

## Known stubs / deferred (not bugs)

- `notify.py` only sends a failure email if `SMTP_HOST`/`ALERT_TO_EMAIL` are set — otherwise it logs and does nothing. Fine to leave unconfigured for this first test; worth setting up before this runs unattended.
- Only script generation is wired into the due-check loop. Nothing else in the 8-step pipeline is touched by this phase.
- If a show's guidelines page is genuinely empty, generation still proceeds with a generic fallback instruction rather than failing — intentional (a blank guidelines page is a valid, if suboptimal, state), but worth noticing if it happens unexpectedly.
