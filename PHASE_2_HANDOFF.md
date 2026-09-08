# Phase 2 handoff — Show setup admin screen

For the session with WPVibe access to `netgain.news`, after Phase 1 (see `PHASE_1_HANDOFF.md`) is already installed and verified. As before: no PHP interpreter was available in the build session, so **run `php -l` on every changed/new file first**, especially `includes/admin/class-edit-show-page.php` (the largest, most template-heavy file).

## What changed since Phase 1

- `includes/class-cpt-vertical.php`: `show_ui` flipped from `false` to `true` (still `show_in_menu => false`).
- New: `includes/class-guidelines.php`, `includes/admin/*` (4 files), `assets/admin.js`, `assets/admin.css`.
- `includes/class-cpt-show.php`: refactored to expose `Net_Gain_CPT_Show::meta_keys()` — same registered fields as before, just restructured so the admin save handler can reuse the list.
- Plugin version bumped to 0.2.0.

Deactivating/reactivating the plugin isn't required for this update (no new tables or roles), but do it anyway if anything seems stale — `Net_Gain_Activator::activate()` is idempotent (`add_role` no-ops if the role exists, `dbDelta` no-ops if the table already matches).

## Click-through test

1. Go to **Net Gain Studio** in the wp-admin sidebar (new top-level menu item). Should show "No shows yet."
2. Click **+ Add New Vertical** from the eventual Show form (or go directly to `wp-admin/post-new.php?post_type=ng_vertical`) and create one, e.g. title "Ed-tech", content = some sample guidelines text. Save.
3. Back in Net Gain Studio → **Add New Show**. Fill in every field: name "Net Gain Edtech", pick the Vertical you just made, a slug, recording days, target time + timezone, publish mode (try "scheduled" — confirm the publish time/timezone row actually appears/disappears when you toggle the radio), lookback days, primary talent (if no `ng_talent`-role user exists yet, create one first via Users → Add New, then set their role, per the on-screen instructions), upload a placeholder image for each of the 3 branding frames via the media picker, status "Active". Save.
4. Confirm you land back on the edit screen for the newly-created show with a "Show saved" notice, and:
   - The Vertical field is now shown disabled, with the note about it being locked.
   - **Editorial guidelines** shows an "Edit Guidelines Page" button — click it, confirm it opens a real WP Page editor in a new tab, and that its content matches what you put in the Vertical.
   - The 3 frame thumbnails render.
   - `GET /wp-json/wp/v2/ng_show/{id}` (as the `ng_service` Application Password, or just as an admin in the browser while logged in) shows all the meta values you entered.
   - `GET /wp-json/net-gain/v1/shows/{id}/talent` shows one row with `role: primary` and the user ID you picked.
5. Fill in the **Connect Captivate show** section with a fake ID and click **Connect** (its own button/form). Confirm it saves independently of the main form (i.e., you can do this without re-submitting the whole show form) and shows a "Captivate show ID saved" notice.
6. Confirm the **Connect YouTube channel** button renders **disabled**, with "Not connected" status text and the explanatory note — clicking it should do nothing (no JS handler is attached to it on purpose).
7. Edit the show again and change its status to "Paused", then "Concluded" — confirm both save cleanly and nothing else on the site changes as a result (nothing to publish/hide yet at this phase, but worth confirming the save path doesn't touch anything beyond the `ng_status` meta value).

## Known stubs (not bugs)

- Captivate ID isn't validated against Captivate's live API here — Phase 5 will add that at episode-publish time.
- YouTube connection is fully inert by design — Phase 9.
- No way yet to *use* a Show for anything (no episodes, no publishing) — that starts in Phase 3.
