# Phase 9 handoff — YouTube publishing

For the session with WPVibe/cPanel access, after Phases 1–8 are installed and at least one show has real Captivate + website publishing working. This phase touches both sides — a plugin install *and* a Python deploy — and needs real setup in Google Cloud Console before either side can be tested end to end.

## Before installing anything: decisions and setup only a human operator can do

1. **Create (or reuse) the GCP OAuth client**, in the same GCP project already used for Vertex AI (CLAUDE.md's credentials table: YouTube must share that project — never a separate one per show, YouTube's API Terms of Service explicitly prohibit "sharding" quota). Under **APIs & Services → Credentials**, create an **OAuth client ID** of type **Web application**. Its **Authorized redirect URI** must be *exactly*:
   ```
   https://netgain.news/wp-json/net-gain/v1/youtube-oauth-callback
   ```
   one static URL for the whole studio, no per-show path — `show_id` travels in the OAuth `state` parameter instead (see `class-rest-secrets.php`).
2. **Enable the YouTube Data API v3** on that same project, if not already enabled.
3. **OAuth consent screen decision — this gates everything downstream.** While this app's consent screen is in Google's **Testing** publishing status, every refresh token Google issues **expires after 7 days**, because the scopes this phase needs (`youtube.upload`, `youtube.force-ssl`) are sensitive. Two paths:
   - If the Google account is part of a **Google Workspace organization**, set the consent screen's user type to **Internal** — no verification needed, no 7-day expiry, done.
   - Otherwise, it must be **External**, and Google's verification process for sensitive scopes (a demo video + a security review, timeline in weeks) needs to be started — **do this now, not after the first "it stopped working after a week" report.** Every already-connected channel will need reconnecting once verification completes and the app leaves Testing status, so plan test connections accordingly in the meantime.
4. **Add two new `wp-config.php` constants** (same pattern as the existing `NET_GAIN_ENCRYPTION_KEY`):
   ```php
   define( 'NET_GAIN_YOUTUBE_CLIENT_ID', 'the OAuth client id, ends in .apps.googleusercontent.com' );
   define( 'NET_GAIN_YOUTUBE_CLIENT_SECRET', 'the OAuth client secret' );
   ```
5. **Phone-verify the test show's YouTube channel** before connecting it — YouTube requires this before any programmatic thumbnail-setting works, confirmed with no exception (Settings → Channel → Feature eligibility, in YouTube's own channel settings). There's no way to fix a missed verification from inside this system after the fact short of reconnecting once it's done.

None of this is something this build session can do — it needs the human operator with access to the actual Google account and Google Cloud Console.

## Install

1. **WordPress**: standard pattern — deactivate → delete → upload the new zip (v0.6.0) → activate. No new tables/roles/rewrite rules this phase (no Permalinks flush needed).
2. **Python**: pull the updated `pipeline/` code and run `pip install -r requirements.txt` inside the existing venv — this pulls in `google-api-python-client`, `google-auth`, and `imageio-ffmpeg` for the first time. **Confirm `imageio-ffmpeg` actually resolved a working binary on this host** — run:
   ```bash
   python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
   ```
   and confirm the printed path exists and is executable. If this fails, YouTube publishing has no usable ffmpeg and will fail loudly (not silently) on every attempt until resolved — see `video_composition.py`'s `ffmpeg_path()` error message.
3. No new Python environment variables this phase — the OAuth client secret and refresh tokens both live entirely in WordPress (see "Two new WordPress routes" below), so `.env`/cPanel's "Setup Python App" variables need no changes.

## The two new WordPress routes, briefly

- `GET /net-gain/v1/youtube-oauth-callback` — Google's own redirect target. Public (no auth check), secured by a single-use `state` parameter instead.
- `POST /net-gain/v1/shows/{id}/youtube-access-token` — what Python calls each tick to mint a short-lived (~1hr) access token. Gated tighter than every other route this project has (`edit_ng_shows` — service account or admin only, not talent). The refresh token and client secret never leave this route's response boundary.

## Click-through test

1. **Connect a real channel.** Go to a show's Edit Show screen → "Connect YouTube channel" → **Connect YouTube Channel**. Confirm it redirects to a real Google consent screen, and after granting access, redirects back showing **Connected**, the real channel title/ID, and (if the channel is phone-verified) no warning banner. If you see the phone-verification warning and you know the channel *is* verified, that's `status.longUploadsStatus` acting as an imperfect proxy (flagged in the plan as unverified against live docs) — worth a closer look, not necessarily a real problem.
2. **Disconnect and reconnect** — confirm both work and the status readout updates correctly each time.
3. **Get a real episode finalized** (script + audio) for a show connected to an *unlisted test channel* (Section 13 — never point a first real test at a live public channel).
4. **Run `tick.py` by hand.** Watch for: metadata generation (if not already done), the pre-publish checklist (should pass silently on reasonable generated metadata), the `in_progress` transition, the ffmpeg render, the upload, and the thumbnail-set attempt.
5. **Check the dashboard immediately after**: the YouTube cell should be **blue** (`in_progress`) with a tooltip explaining the processing delay is expected, not a failure.
6. **Run `tick.py` again a few minutes later** (YouTube's real processing delay). Confirm the cell resolves to **green** (`done`), the episode's `ng_url_youtube` is a real, working watch URL, and the video is visibly `unlisted` with the right title/description/tags when you open it.
7. **Deliberately break a checklist criterion** — e.g., temporarily shorten `metadata_generation.py`'s tag-count instruction to produce only 1–2 tags, or manually clear `ng_meta_youtube_tags` on a test episode via the REST API — and confirm the step goes **red** (`failed`) with a note naming the *specific* failed criterion, not a generic error.
8. **Confirm an unconnected show's YouTube cell is gray**, not red, with a "no channel connected" tooltip — and confirm that show's episodes are no longer piling up in `in_flight_episodes` indefinitely (the pre-existing bug this phase fixes — check via `GET /net-gain/v1/tick-context` directly if you want to see the raw payload).
9. **Try the manual trigger**: on the Episode Detail page, click **Publish to YouTube** (or **Re-check YouTube publish** once already published) on a finalized episode and confirm it queues and the next tick picks it up, same as the existing Captivate trigger.

## Known stubs / deferred (not bugs)

- No UI to regenerate just an episode's YouTube metadata once it exists — a checklist failure's only recovery path today is the manual `publish_youtube` trigger, which re-checks/re-uploads but does not force fresh metadata generation. If this turns out to matter in practice, the fix is a dedicated `generate_metadata` manual action, not a YouTube-specific one.
- No automated handling of YouTube's quota ceiling (~6 uploads/day across the whole studio on the default quota) beyond the per-episode cost noted in `SPEC.md` Section 6.3 — file Google's quota-increase request once a 5th show is onboarded, not when an upload first fails with a quota error.
- The "known unresolved risk" SPEC Section 6.3 already names (YouTube's spam/templated-content enforcement at scale) has no code-level mitigation beyond each show's genuinely distinct script/voice — worth a closer look once enough live channels exist for a real pattern to become visible.
- `video_composition.py`'s exact ffmpeg flags (especially `-r 1`, 1fps) are this build's best understanding, not proven against a real render on this specific host — the first real upload is also the first real test of this.
