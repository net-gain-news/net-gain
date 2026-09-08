# Phase 1 handoff — Net Gain Studio plugin

For the session with WPVibe access to `netgain.news`. This session (Claude Code) has no PHP interpreter available locally, so verification here was limited to manual review plus a raw brace/paren balance check on every file — no `php -l` was run. **Run `php -l` on every file in `net-gain-studio/` as your first step**, before activating.

## What was built

Phase 1 of the build order in `CLAUDE.md`: the data model (Vertical, Show, Talent, Episode) as WordPress custom post types + custom tables, and the `net-gain/v1` REST API surface. No admin UI yet (Phase 2) — this is data/REST plumbing only. Design rationale is in `net-gain-studio/README.md` and the approved plan.

## Install steps

1. `php -l` every file (see above).
2. Add to `wp-config.php`: `define( 'NET_GAIN_ENCRYPTION_KEY', '<generate a long random string>' );` — required before the secrets table can store anything.
3. Install/activate the plugin (via WPVibe) from `net-gain-studio/`.
4. Confirm activation created: 3 custom post types (`ng_vertical`, `ng_show`, `ng_episode` — check via `wp post-type list` or the REST index at `/wp-json/wp/v2/`), 2 new tables (`wp_ng_talent_assignments`, `wp_ng_secrets`), 2 new roles (`ng_service`, `ng_talent` — check Users → Roles or `wp role list`).
5. Create a WordPress user with the `ng_service` role, then generate an Application Password for it (Users → your profile → Application Passwords). That credential is what the Python pipeline will authenticate with in a later phase.

## Functional checks

Using the `ng_service` Application Password (Basic Auth: `username:application-password`):

1. `GET /wp-json/net-gain/v1/tick-context` → should return `[]` (no Active shows yet).
2. `POST /wp-json/wp/v2/ng_show` with a title and `meta.ng_status = "active"` → create a test show; confirm it comes back from `tick-context` on the next call.
3. `POST /wp-json/net-gain/v1/shows/{id}/actions` with `{"action":"generate_script"}` → confirm it shows up in that show's `ng_pending_actions` and in `tick-context`'s output for that show.
4. `POST /wp-json/wp/v2/ng_episode` with `parent = {show_id}` → create a test episode.
5. `PATCH /wp-json/net-gain/v1/episodes/{episode_id}/steps/images_rendered` with `{"status":"done"}` → **should fail with a 409** (prerequisite `metadata_generated` not done yet) — this is the one behavior most worth confirming, since it's the mechanism the whole idempotency/manual-trigger design (Section 8.3) depends on.
6. `PATCH .../steps/script_generated` then `.../steps/script_reviewed` then `.../steps/audio_received` then `.../steps/metadata_generated` then `.../steps/images_rendered`, each `{"status":"done"}`, in that order → each should succeed once its prerequisite is satisfied.
7. `POST /wp-json/net-gain/v1/shows/{id}/secrets/youtube-oauth` with `{"payload":{"test":true}}`, then `GET .../secrets/youtube-oauth/status` → should return `{"connected": true}`. Spot-check the `wp_ng_secrets` table directly to confirm `ciphertext` is not plaintext.
8. Confirm a plain logged-out request (no auth) to any `ng_show`/`ng_episode` REST route gets rejected — both post types are `public => false`, so this should already be the case, but worth a direct check since a mistake here would leak pipeline data.

## Known stubs / deferred work (not bugs)

- `/shows/{id}/secrets/youtube-oauth` just encrypts and stores whatever payload it's given — the real OAuth authorization flow is a later (YouTube) phase.
- `ng_website_post_id` on Episode has no writer yet — Phase 6 wires it up.
- No admin UI exists yet — everything above is exercised via raw REST calls. Phase 2 builds the show-setup screen.

## Clean up after testing

Delete the test show/episode created in step 2–4 above once verified, or leave them — they don't affect anything since no automation reads them yet.
