# Phase 6 handoff — Website publishing + AIOSEO + schema

For the session with WPVibe/cPanel access, after Phases 1–5 are installed and at least one episode has a real Captivate publish working (or is at least finalized and ready).

## Install — three things beyond the usual plugin swap

1. **Deactivate → delete → upload the new zip → activate**, as always. This phase's activation matters more than usual: it's what applies the new `ng_service` capabilities (`edit_posts`, `edit_pages`, `publish_posts`, `publish_pages`, `manage_categories` — needed because this phase creates real WordPress Posts, Pages, and taxonomy terms, none of which the service account could touch before).
2. **Flush rewrite rules**: go to **Settings → Permalinks** and click **Save** (no changes needed, just visiting and saving forces WordPress to recompile its cached rewrite rules). This phase adds a new URL pattern (`/shows/{show-slug}/{episode-slug}/`) that won't actually resolve until this happens — adding the rule in code doesn't retroactively update what's already cached.
3. **Confirm Seriously Simple Podcasting is active** — this entire phase depends on it (the `podcast` post type and `series` taxonomy it registers). If the `/wp-json/net-gain/v1/episodes/{id}/publish-website` call fails with "does not exist - is Seriously Simple Podcasting active?", that's the literal problem, not a bug.

## The one thing that genuinely needs live confirmation

AIOSEO's own docs say the `aioseo_save_post` filter hands you an internal `Post` model object whose property names are "subject to change," and recommend inspecting it live rather than trusting documentation. This build used `$post->title` and `$post->description` as the most likely names (see `class-aioseo-integration.php`) — **not confirmed**. To check: publish a real episode, then look at that episode's live page — does the browser tab title / the page's `<title>` tag (view source, or an SEO checker) actually show the generated AIOSEO title, or AIOSEO's own default? If it's not showing up, add a quick `error_log(print_r($post, true));` inside `filter_save_post()` temporarily, publish again, and check the PHP error log for the real property names — then tell me what they actually are so I can fix the code to the confirmed names instead of the current guess.

## Click-through test

1. Get a real episode finalized with a real final script and audio (Phases 3–4).
2. Run `tick.py` by hand. Watch for: metadata generation (if not already done from a Captivate test), then a website-publish attempt, then the independent re-fetch-and-verify step.
3. Confirm the episode actually landed at **`/shows/{show-slug}/{episode-slug}/`** — not a flat `/podcast/{episode-slug}/` URL. This is the one most worth checking by hand; if the rewrite rules weren't flushed (step 2 above), it'll silently 404 or fall back to SSP's default flat URL instead.
4. Visit **`/shows/`** — confirm the auto-created "Our Shows" page exists and lists every Active/Concluded show.
5. Visit **`/shows/{show-slug}/`** — confirm the show's own hub page exists and lists its published episodes.
6. View the published episode page's source and confirm a `<script type="application/ld+json">` block is present with `"@type": "PodcastEpisode"`.
7. Confirm the post's author byline shows the actual recording talent, not a generic site admin.
8. Confirm `GET /wp-json/wp/v2/ng_episode/{id}` shows `meta.ng_website_post_id` and `meta.ng_url_website` populated, and `meta.ng_step_status.website_published` reads `done`.

## Known stubs / deferred (not bugs)

- `cover_image_id` is never set yet — Phase 8 (images) hasn't been built, same non-blocking pattern as Captivate's `episode_art` in Phase 5.
- `duration`/`filesize`/`date_recorded` on the SSP episode aren't set — optional fields SSP can derive on its own; not required for the page or player to work.
- YouTube publishing (Phase 9) isn't touched by this phase at all.
