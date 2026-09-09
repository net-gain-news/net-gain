# Net Gain Studio (WordPress plugin)

Phases 1–6 of the Net Gain multi-tenant newscast studio build — see `../SPEC.md` and `../CLAUDE.md` for the full design. Phase 5 (Captivate publishing) is almost entirely on the Python side — see `../pipeline/README.md` — the one plugin change was adding a `finalized_at` timestamp to `ng_finalization` so scheduled-publish timing can be computed correctly. Phase 6 (website publishing) is the opposite: almost entirely this plugin, since it runs inside the same WordPress process as the audio file.

## What's here

**Phase 1 — data model + REST:**
- **Custom post types**: `ng_vertical`, `ng_show`, `ng_episode` — all `public => false`, all `show_in_rest => true`, each with its own `capability_type` so they're isolated from ordinary WordPress Posts. `ng_vertical` has `show_ui => true` (as of Phase 2) so it gets WordPress's native title+editor screen with no nav menu entry — no custom Vertical admin code exists or is needed.
- **Custom tables**: `wp_ng_talent_assignments` (talent↔show many-to-many + substitute date ranges) and `wp_ng_secrets` (encrypted per-show/global secrets, e.g. YouTube OAuth tokens).
- **Custom roles**: `ng_service` (the account Python authenticates as via a WordPress Application Password) and `ng_talent`.
- **REST routes**: default CPT REST for `ng_vertical`/`ng_show`/`ng_episode`, plus a custom `net-gain/v1` namespace for cross-entity operations (tick-loop context, manual-trigger actions, talent assignment, per-step status updates, finalization abort/publish-now, secrets).

**Phase 2 — Show setup admin screen:**
- A "Net Gain Studio" top-level admin menu (Shows list) plus a hidden Add/Edit Show page reached via links, not its own nav item.
- Implements every field in Spec Section 11: recording/publish schedule, timezones (via core's `wp_timezone_choice()`), lookback window, primary talent (writes to `wp_ng_talent_assignments`, not postmeta), branding-frame uploads (via core's `wp.media` picker — no build step), a guidelines page auto-seeded once from the chosen Vertical's content, and Show status.
- "Connect Captivate show" saves an ID via its own form/action. "Connect YouTube channel" is a **visibly disabled** control with a status readout — real OAuth is Phase 9, not faked here.
- Plain PHP-rendered pages + one vanilla-JS file (`assets/admin.js`) — no JS build tooling anywhere in this plugin.

**Phase 4 — Review, finalization & queue:**
- **Script review** (`class-script-review-page.php`): full-width final-script editor, AI draft behind a collapsed toggle, PHP `similar_text()` similarity check that marks a suspiciously-close save `degraded` rather than `done`.
- **"My Show"** (`class-my-show-page.php`) — the first talent-facing screen, gated by the talent-assignment relationship rather than a WordPress role. Audio upload via `wp.media` (filtered to audio) immediately starts a server-truth finalization countdown; the visible timer is a reflection of that state, not its source — `pipeline/tick.py` independently detects an elapsed countdown even if no browser is watching.
- **Episode detail/queue view** (`class-episode-detail-page.php`, reached via a new Episodes list per show): every deliverable with a direct action, plus the Section 8.3 manual triggers (Generate/Regenerate Script, Generate Images, Publish Captivate), prerequisite-aware disabling.
- **Two build-time corrections to the original spec text**, now reflected in `SPEC.md` itself: metadata generation is deferred until close to publish time rather than triggered at finalization (avoids wasted work on later-aborted episodes), and image generation no longer depends on metadata generation, so it stays manually triggerable at any time.

**Phase 6 — Website publishing + AIOSEO + schema:**
- `class-rest-website-publish.php`: creates the real public episode page at publish time — Seriously Simple Podcasting's own `podcast` post type, which we confirmed (from its actual source, not a guess) uses a single flat rewrite slug rather than nesting under its `series` taxonomy.
- `class-website-rewrite.php`: a custom `post_type_link` filter + `add_rewrite_rule()` that actually produces `/shows/{show-slug}/{episode-slug}/`, since Seriously Simple Podcasting doesn't do that nesting on its own.
- `class-aioseo-integration.php`: real AIOSEO hooks (`aioseo_description` filter, and `aioseo_save_post` — which the spec calls an "action" but AIOSEO's own docs call a filter). No `aioseo_title` filter exists (confirmed against AIOSEO's full documented hook list), so the SEO title goes through `aioseo_save_post`'s internal `Post` model instead — its exact property names are undocumented ("subject to change" per AIOSEO itself), so this needs live confirmation; see `PHASE_6_HANDOFF.md`.
- `class-schema-output.php`: hand-rolled `PodcastEpisode` JSON-LD via `wp_head`, per the spec's own instruction not to assume AIOSEO supports this schema type (confirmed it doesn't).
- `includes/shortcodes/class-shortcodes.php`: `[net_gain_shows_hub]` (the cross-show "all our shows" page) and `[net_gain_show_episodes]` (a single show's episode list) — both auto-placed on lazily-created hub pages (`/shows/` and `/shows/{slug}/`).
- `ng_service` gained `edit_posts`/`edit_pages`/`publish_posts`/`publish_pages`/`manage_categories` — needed because this phase creates real WordPress Posts, Pages, and taxonomy terms, none of which were covered by the plugin's own `ng_show`/`ng_episode` capability types.

## Setup required at install time

Add to `wp-config.php` before activating (needed for the secrets table to actually encrypt anything):

```php
define( 'NET_GAIN_ENCRYPTION_KEY', 'a long random string, generate once and never change' );
```

After activation, create an Application Password for a user with the `ng_service` role — that's what the Python pipeline authenticates with.

## Deliberately not built yet

- The real YouTube OAuth flow (`/shows/{id}/secrets/youtube-oauth` currently just stores whatever payload it's given — see the `TODO(youtube-phase)` marker in `includes/rest/class-rest-secrets.php`; the admin screen's YouTube button is disabled for the same reason).
- Live Captivate validation at connect-time (Section 6.1's verification happens at episode-publish time, Phase 5) — the admin screen just saves the ID.
- The operations dashboard (Phase 7) — episode status is only visible via the Episodes list, episode detail view, and raw REST calls for now.
- `cover_image_id` on the public episode post, and `episode_art` on Captivate — both wait on Phase 8 (images); neither blocks publishing in the meantime.
- Real image generation and YouTube publishing — the manual-trigger buttons in the episode detail view queue an intent that nothing processes yet (Phases 8, 9).
