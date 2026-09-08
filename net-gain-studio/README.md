# Net Gain Studio (WordPress plugin)

Phase 1 of the Net Gain multi-tenant newscast studio build — see `../SPEC.md` and `../CLAUDE.md` for the full design. This phase is data model + REST plumbing only: no admin UI screens yet (Phase 2).

## What's here

- **Custom post types**: `ng_vertical`, `ng_show`, `ng_episode` — all `public => false`, all `show_in_rest => true`, each with its own `capability_type` so they're isolated from ordinary WordPress Posts.
- **Custom tables**: `wp_ng_talent_assignments` (talent↔show many-to-many + substitute date ranges) and `wp_ng_secrets` (encrypted per-show/global secrets, e.g. YouTube OAuth tokens).
- **Custom roles**: `ng_service` (the account Python authenticates as via a WordPress Application Password) and `ng_talent`.
- **REST routes**: default CPT REST for `ng_vertical`/`ng_show`/`ng_episode`, plus a custom `net-gain/v1` namespace for cross-entity operations (tick-loop context, manual-trigger actions, talent assignment, per-step status updates, finalization abort/publish-now, secrets).

## Setup required at install time

Add to `wp-config.php` before activating (needed for the secrets table to actually encrypt anything):

```php
define( 'NET_GAIN_ENCRYPTION_KEY', 'a long random string, generate once and never change' );
```

After activation, create an Application Password for a user with the `ng_service` role — that's what the Python pipeline authenticates with.

## Deliberately not built yet

- The real YouTube OAuth flow (`/shows/{id}/secrets/youtube-oauth` currently just stores whatever payload it's given — see the `TODO(youtube-phase)` marker in `includes/rest/class-rest-secrets.php`).
- Wiring `ng_episode` to an actual public Seriously Simple Podcasting post at publish time (Phase 6) — `ng_website_post_id` is reserved for this.
- Anything in the admin UI (Phase 2) or the Python tick loop itself (Phase 3+).
