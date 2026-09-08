# Net Gain Studio (WordPress plugin)

Phases 1–2 of the Net Gain multi-tenant newscast studio build — see `../SPEC.md` and `../CLAUDE.md` for the full design.

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

## Setup required at install time

Add to `wp-config.php` before activating (needed for the secrets table to actually encrypt anything):

```php
define( 'NET_GAIN_ENCRYPTION_KEY', 'a long random string, generate once and never change' );
```

After activation, create an Application Password for a user with the `ng_service` role — that's what the Python pipeline authenticates with.

## Deliberately not built yet

- The real YouTube OAuth flow (`/shows/{id}/secrets/youtube-oauth` currently just stores whatever payload it's given — see the `TODO(youtube-phase)` marker in `includes/rest/class-rest-secrets.php`; the admin screen's YouTube button is disabled for the same reason).
- Wiring `ng_episode` to an actual public Seriously Simple Podcasting post at publish time (Phase 6) — `ng_website_post_id` is reserved for this.
- Live Captivate validation at connect-time (Section 6.1's verification happens at episode-publish time, Phase 5) — the admin screen just saves the ID.
- Episode-facing UI (script review, audio upload, the operations dashboard) or the Python tick loop itself (Phase 3+).
