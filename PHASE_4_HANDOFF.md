# Phase 4 handoff — Review, finalization & queue

For the session with WPVibe/cPanel access, after Phases 1–3 are installed and a real Show has at least made it through script generation (Phase 3) once. Same caveat as before: no PHP interpreter in the build session, so **run `php -l` on every changed/new file first** — this phase touches significantly more PHP than any previous one.

## What changed since Phase 3

- **Plugin bumped to 0.3.0.** New files: `class-script-review-page.php`, `class-my-show-page.php`, `class-episodes-list-page.php`, `class-episode-detail-page.php`. Changed: `class-admin-menu.php`, `class-admin-actions.php`, `class-rest-episode-steps.php`, `class-rest-show-actions.php`, `class-cpt-show.php`, `class-step-status.php`, `class-shows-list-page.php`, `assets/admin.js`.
- **`pipeline/tick.py`** gained a finalization-countdown-elapse check (`check_finalizations`) and a `force`-flag bypass on the existing idempotent skip.
- **`SPEC.md` was amended** (Sections 8.1, 8.2, 8.3) to reflect two real design corrections made during this build — see below. Worth reading those inline amendments directly in the spec.

## Two things that changed from how earlier phases described this

1. **Metadata generation is not triggered by finalization.** It's deliberately deferred until close to a show's actual publish moment (not built yet — a later phase), to avoid wasted work on episodes later aborted and replaced. A finalized episode will show `metadata_generated: pending` and that's correct, not a bug.
2. **Image generation no longer depends on metadata generation.** The two are now sibling steps (both depend only on `audio_received`), specifically so images stay manually triggerable at any time regardless of metadata's timing. Only the three publish steps (Captivate/website/YouTube) require both.

## Install

Same pattern as before: deactivate → delete → upload the new zip → activate. No new tables/roles this phase, so reactivation is just a code swap. Also update `pipeline/` on Canspace with the changed `tick.py` (and the new test files if you want them there, though they're dev-only and never executed in production).

## Click-through test

1. **Script review.** With an episode that has a script draft (Phase 3), find it via Net Gain Studio → your show's Episodes link → the episode → Open Script Review. Confirm: the AI draft is hidden behind "Show AI draft" and toggles correctly; saving with the text essentially unchanged marks the step `degraded` with a "flagged for a second look" notice (check `GET /wp/v2/ng_episode/{id}` → `meta.ng_step_status.script_reviewed`); saving with substantial edits marks it `done` instead.
2. **My Show (as the talent, not admin).** Log in as (or impersonate) the assigned talent user. Confirm **My Show** appears in their sidebar and shows the right episode once its script is reviewed. Click **Upload Audio**, pick or upload an audio file via the media picker. Confirm the countdown appears and actually ticks down in the browser.
3. **Countdown resolves without the tab open.** Start a countdown, then close the browser tab entirely before it reaches zero. Wait past the countdown duration plus one tick-loop interval, then check `GET /wp/v2/ng_episode/{id}` → `meta.ng_finalization.state` — it should read `finalized` even though no browser ever saw it happen. This is the one behavior most worth confirming; it's the whole point of the countdown being server-truth, not UI-truth.
4. **Abort and replace.** Start a new episode's countdown, click **Abort**, confirm state becomes `awaiting_replacement` and the upload widget reappears; upload again and confirm a fresh countdown starts.
5. **Publish Now.** Start a countdown, click **Publish Now**, confirm `ng_finalization.state` becomes `finalized` immediately (not after a wait).
6. **Manual triggers + regenerate.** As admin, open an episode's detail view (Net Gain Studio → Episodes → an episode). Click **Generate Images** — confirm a pending action appears on the show (`GET /net-gain/v1/shows/{id}/actions`) with `force: false`; nothing actually renders images yet (Phase 8 isn't built), which is expected. On a script that's already `done`, confirm the button now reads **Regenerate Script**, and that clicking it produces a pending action with `force: true`, and that the *next* `tick.py` run actually overwrites `ng_script_draft` with a new draft rather than skipping (this is the specific behavior Phase 4 added — worth confirming directly, since the old idempotent-skip behavior would have silently ignored this).
7. **Prerequisite-disabled buttons.** On a brand-new episode with no audio yet, confirm **Generate Images**' button is disabled (not just unstyled — actually has the `disabled` attribute) with a tooltip naming the unmet prerequisite.

## Known stubs / deferred (not bugs)

- Generate Images / Publish Captivate buttons queue an action that nothing currently processes — Phases 5 and 8 add the actual processors. The point of testing them now is just confirming the queue mechanism and prerequisite gating work, not that anything visibly happens.
- Abort/Publish Now only work during the audio-intake countdown (`state: counting_down`). Applying them to an already-finalized, queued-for-real-publish episode is future-phase work once real scheduled publishing exists.
- No dashboard exists yet (Phase 7) — episode status is only visible via the Episodes list, episode detail view, and raw REST calls.
