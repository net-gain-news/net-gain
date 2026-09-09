# Phase 7 handoff — Operations dashboard

For the session with WPVibe access, after Phases 1–6 are installed. This phase is entirely PHP — no Python changes, no new credentials.

## Install

Standard pattern: deactivate → delete → upload the new zip (v0.5.0) → activate. No new tables/roles/rewrite rules this phase — a Permalinks flush isn't needed for this one.

## Heads up: the main menu changed

**"Net Gain Studio" in the sidebar now opens the Dashboard by default, not the Shows list.** Shows management is still there — it's now its own visible submenu item ("Shows"), just no longer the landing page. This was a deliberate call (the dashboard is the daily-use screen; show setup is occasional), flagged here so it doesn't read as a bug on first look.

## Click-through test

1. Open **Net Gain Studio** — confirm it lands on the Dashboard, showing today's date, with every Active show as a row and all 8 step columns.
2. Click **Previous day** / **Next day** / **Today** — confirm the date and grid actually change, and a day with no episode for a show shows all-gray for that row rather than erroring.
3. On a real episode with some steps done and some not: hover each LED and confirm the tooltip text is specific and useful, not a blank tooltip or a PHP warning leaking into the page. Specifically check:
   - A `failed` step's tooltip (if you have one to test with, or trigger one) — should name the actual thing to check, not generic "see logs."
   - `script_reviewed` marked `degraded` (a near-identical save from Phase 4's testing) — amber, not red, with the "second look" wording.
   - The `youtube_published` column — should read as a distinct "not built yet (Phase 9)" tooltip, not a bare "not reached."
4. Click a few LEDs that should be links (final script → Script Review; the audio LED → the actual audio file; a Captivate/website LED once one is truly published → the live page) — confirm they open in a new tab and go to the right place. A LED with nothing behind it yet (e.g. `images_rendered` pre-Phase-8) should still be clickable through to the Episode Detail page, not dead.
5. **Resize the browser narrow (or check on an actual phone)** — confirm the table genuinely restacks into cards with labels, rather than just becoming a tiny horizontally-scrolling table. This is the one most worth checking on a real narrow viewport, not just a resized desktop window, since some responsive CSS bugs only show up with real touch/viewport behavior.
6. Mark a show as a **Test show** (new checkbox on its setup screen) — confirm it disappears from the main dashboard grid and instead appears, correctly collapsed, under a **"Test shows"** disclosure at the bottom. Click the disclosure and confirm it expands to show that show's row.
7. Start a countdown (My Show → upload audio) and check the dashboard **while it's still counting down** — the Audio column should show the pulsing blue LED, not solid green, even though the step itself is technically "done." Then abort it and confirm the Audio LED drops back to gray (the Phase 4 bug this phase fixed).

## Known stubs / deferred (not bugs)

- The `images_rendered` and `metadata_generated` columns link to the Episode Detail page rather than a specific artifact — there's no single "the image" to link to (three separate images, per Section 7) and no natural single-artifact page for metadata; the detail page is the practical landing spot for both.
- Everything in the YouTube column reads Gray with an explicit "not built yet" tooltip — accurate, not a placeholder oversight.
