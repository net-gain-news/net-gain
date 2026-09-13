# Multi-Tenant Newscast Studio — Project Specification

**Status:** Design complete, not yet built. This document is a project brief intended for a Claude Code build session.

## 1. Background & Origin

This system evolves from a working single-show pipeline ("Net Gain," a daily good-news podcast) that was built and debugged extensively before being repurposed. The original eponymous Net Gain show itself is **not going forward** — the underlying automation it proved out (script generation via Claude, audio publishing to Captivate, GitHub Actions/Canspace cron scheduling) is being generalized into a **multi-tenant vertical newscast studio**: a business that produces branded, sponsor-underwritten daily newscasts for different verticals (financial advisors, real estate, and others as they arise), each independently produced and independently voiced. The original single-show scripts and automation are being **left running, untouched, as-is** until a deliberate future decommission — the new system is entirely separate infrastructure, not a migration of the old one.

**First live vertical: Net Gain Edtech.** This is the first real (non-hypothetical) Show Instance, with an active editorial guidelines doc in progress and a target to begin publishing imminently. Talent (recording voice, and therefore the website post author / EEAT profile) is Dallas Kachan. No historical recordings exist or need to be migrated — this show starts fresh. Given the full multi-tenant system will not be built and tested by the time this show is ready to start, early episodes may be produced and published manually (by hand, outside any automated pipeline) as a bridge — this is expected and does not require building an interim automated system.

Key lessons carried forward from the Net Gain build, referenced throughout this spec:
- Claude Sonnet 5 requires `thinking: {"type": "disabled"}` for tool-heavy generation calls, or adaptive thinking silently consumes the entire token budget before any output is produced.
- Long agentic tool-use turns can return `stop_reason: "pause_turn"`; continuing requires appending the paused content as an assistant turn *followed by* a fresh user turn (this model does not support assistant-message prefill).
- Third-party API field names should never be assumed — verify against the provider's actual documentation or a live response before building on top of a guess. (Captivate's real scheduling field is `date`, format `YYYY-MM-DD HH:mm:ss`, not any of the plausible-sounding alternatives tried first.)
- Cron environments have minimal `PATH` (use absolute binary paths) and treat unescaped `%` as a literal newline (escape as `\%` in any command using `curl -w`).
- Never assume a host's cron runs in UTC — confirm the actual server timezone empirically (a disposable sanity-check cron job that logs `date` output is the fastest way).

## 2. Business Model

### 2.1 Verticals and Show Instances
Two distinct concepts, not one:
- **Vertical**: a reusable show identity and starting editorial template (e.g., "Net Gain Investor," "Net Gain Real Estate"). Not itself published — a template.
- **Show Instance**: one underwriter's live deployment of a vertical. Has its own Captivate feed, own WordPress subdirectory, own schedule, own talent assignment, own guidelines (cloned from the vertical template, then fully customizable), own branding frames.

A new client in an existing vertical = clone the vertical's template into a new Show Instance, then customize. Multiple competing underwriters **can** run separate instances of the same vertical simultaneously — this is an intentional, supported scenario, not an edge case.

### 2.2 Underwriting Model
- Shows remain branded as "Net Gain [Vertical]," **not** white-labeled to the underwriter's own identity. Billed/marketed as e.g. "Net Gain Investor by Assante." This is deliberate: it gives plausible deniability that the content is the underwriter's own editorial product, which matters for compliance in regulated verticals like financial services.
- **Non-exclusive underwriting is the default/base tier.** Category exclusivity (locking out competitors in the same vertical) is offered as a distinct, explicitly priced **premium tier** — industry-standard practice for podcast/newsletter sponsorship is a 20–50% premium for exclusivity, never an assumed default. This preserves the ability to sell the same vertical to multiple competing underwriters simultaneously, each getting their own separately-generated, separately-voiced instance.
- Each competing instance in a shared vertical **must** get independently generated scripts and independently recorded voice talent — never shared or identical content across competing sponsors, for both value and ethical reasons.
- Post-roll advertising is handled **entirely within Captivate's own ad insertion system** (dynamic/programmatic ad slots). This pipeline never touches ad audio, never does host-read ads, and requires no audio-splicing capability of its own.

### 2.3 Compliance
Financial-vertical content may carry real regulatory considerations (suitability, disclosure language). Any required disclaimer text is accommodated through the normal editorial-guidelines mechanism (the guidelines doc drives script generation) — no separate compliance subsystem is being built. **Real compliance/legal review is required before launching any regulated vertical** — explicitly out of scope for this spec to resolve.

## 3. Infrastructure Architecture

### 3.1 Hosting
Everything runs on **Canspace** (not Pressable) — both the WordPress installation and the Python script execution, on the same account.

- **Python execution**: confirmed supported via cPanel's "Setup Python App" tool (per Canspace's own documentation) — provisions a real virtual environment with a selectable Python version and full `pip install` support. Not universally available on every Canspace server; if absent from the account's current server, Canspace migrates the account to a supporting server **at no charge** via a support ticket. No paid upgrade is ever required.
- **Execution model**: cron invokes the Python virtual environment's binary **directly as a CLI process** — never through a web request. This is the same reasoning that made the original `curl` cron jobs work: CLI-invoked processes are not subject to any PHP-FPM/web-server execution-time ceiling. This fully resolves the earlier concern about long-running script-generation calls (which can take minutes) getting cut off — that concern only applied to web-triggered execution, which was never the plan.
- **Scheduling**: a **single Canspace cron entry** (a "tick" endpoint) replaces the old per-client cron-job pattern. It fires frequently and, on each tick, loops through every `Active` show in the database and determines what (if anything) is due. Onboarding client N+1 becomes a database row via the admin UI — never a new cPanel cron job.
- **Concurrency**: each show's processing (both scheduled script generation and audio-upload-triggered publish) must run as a **fully independent, isolated process** with no shared lock or queue across shows. Two shows publishing at the same real-world moment is an expected, supported scenario, not a race condition to prevent.

### 3.2 Removed Dependencies
- **GitHub Actions is removed entirely as a compute/runtime layer.** Canspace cron invokes the Python scripts directly. GitHub Actions' own `schedule` trigger had a confirmed, unresolved platform-side reliability problem (per direct correspondence with GitHub Support: documented delays and dropped runs since May 2026, no ETA) — this was the original reason Canspace cron was introduced to trigger `workflow_dispatch` as a workaround. Removing GitHub Actions as the compute layer removes that failure class entirely, and also removes the GitHub Actions minutes budget as a constraint at N-client scale.
- **GitHub is retained *only* as the source code repository** — version history, backup, and the place code is edited/reviewed before being deployed to Canspace. No live operational dependency. The new system lives in its own dedicated repository, `net-gain` (Section 14) — entirely separate from the existing `net-gain-automation` repository, which keeps running the old single-show pipeline untouched. (A dedicated search for a WordPress-native replacement for this role found nothing suitable — the closest plugins either still depend on git underneath, e.g. Gitium, or only cover WordPress.org-published plugins/themes, e.g. WP Rollback. GitHub-as-repository stands.)
- **Google Drive is removed entirely.** It previously served three roles, each now replaced:
  - *Audio file exchange*: replaced by a WordPress-native upload surface, writing directly to the Canspace filesystem the Python scripts already run on. This also **eliminates** (not just relocates) the old file-stability-polling logic (`appProperties`, `lastSeenSize`, waiting for two consecutive polls to agree) — a completed HTTP upload is its own unambiguous completion signal, unlike a Drive sync.
  - *Text document storage* (Script, Archive, Guidelines, Boilerplate): becomes WordPress-native. Guidelines becomes a full WordPress content page (rich HTML editor, not a plain textarea — these documents run long and need real formatting). Archive becomes a proper database table, one row per episode — this also structurally eliminates the `\r\n` line-ending compounding bug that previously corrupted the growing single-document archive.
  - *Freshness/stability signaling*: no longer needed given the above.

### 3.3 Secrets vs. Configuration
- **True secrets requiring encryption at rest**: Anthropic API key, Captivate login/API token, Google Cloud/Vertex AI credentials (for AI image generation), and **per-show YouTube OAuth tokens** (one set per channel — genuinely sensitive bearer credentials, not just configuration).
- **Non-secret configuration** (most of what lives in the database): Drive-replacement doc/folder references no longer apply; schedule times, subdirectory slugs, lookback window days, talent assignments, etc. do not need encryption-grade handling.
- Most true secrets (Anthropic key, Captivate login, Google Cloud credentials) are shared across all shows — they belong to the studio, not the client. Only YouTube OAuth tokens are genuinely per-show secrets.

### 3.4 WordPress Theme & Podcast Plugin
**Astra** (theme) + **Seriously Simple Podcasting** (plugin) — installed and active on `netgain.news`. Chosen deliberately over an all-in-one podcast marketplace theme (Podover was the original candidate): Astra is Gutenberg/full-site-editing native rather than page-builder-dependent, which matters directly for a pipeline that creates every episode page programmatically — a page-builder-bundled theme risks only rendering correctly for content built by hand in its own editor. Seriously Simple Podcasting registers a real, standard WordPress custom post type for episodes with proper feed/taxonomy support, which our plugin writes into through normal WordPress APIs rather than reinventing an episode post type from scratch.

## 4. Data Model (conceptual)

- **Vertical**: name, starting/template guidelines text.
- **Show**: name, vertical reference, subdirectory slug, optional custom domain, recording days, target time, **explicit timezone** (decoupled from talent's physical location — anchors to the show's own audience, not wherever the talent happens to live), recent-script lookback window (days, per-show configurable), guidelines (link to a WordPress content page), three branding frame files (square/16:9/1200×630), status (Active / Paused / Concluded), primary talent reference, YouTube channel credentials, Captivate show ID.
- **Talent**: modeled as its own entity with a **many-to-many relationship to shows** — not a single fixed field per show. Supports one primary talent per show plus other talent designated as eligible **substitutes** for specific date ranges (vacation coverage). A talent account with access to more than one show (own + covering) must explicitly select which show a given recording is for at upload time — the system never guesses.
- **Episode**: show reference, date, AI draft script text, final reviewed/edited script text, master audio file reference, three rendered image file references, generated metadata (Captivate title/notes, AIOSEO fields, YouTube title/description/tags), resulting published URLs (Captivate, website, YouTube), per-step verification status and timestamps, talent-who-recorded-this-episode reference. **This is a real persisted historical record, not just today's dashboard state** — it must support date navigation/pagination in the admin UI, and it's the source for the recent-scripts dedup context.

### 4.1 Prospective-Only Changes (general principle)
Guidelines edits, talent reassignment, and branding-frame changes **all apply prospectively only, never retroactively.** A new frame affects tomorrow's episode, not the archive. A show's talent reassignment does not change who past episodes are attributed to. This is one general rule, not three unrelated special cases.

### 4.2 Show Status Semantics
- **Active**: normal operation.
- **Paused**: automation stops entirely; nothing else touched (Drive-replacement content, Captivate feed, website page all remain exactly as they are); resumable instantly by flipping back to Active.
- **Concluded** (never "Archived" — that term implies content going away, which is explicitly not the intent): stops new episode production only. Already-published content (Captivate feed, website page, back catalog) is **never removed or hidden** as a consequence of status change — this is a hard, general rule: production status controls whether *new* episodes get made, never whether *existing* ones stay live.

## 5. Content Pipeline

### 5.1 Script Generation
- Each generation call includes the show's own past N days of *reviewed, final* scripts as literal context, alongside the guidelines — N is the per-show configurable lookback window. This is real transcript context for duplicate-story suppression, not just an instruction to "avoid repeating stories" (which does not work reliably on its own, since each generation is a fresh conversation with no memory of prior days).
- **Editorial-preference learning (added 2026-09-12)**: for episodes within that same lookback window where the host's edit was substantial — i.e., `script_reviewed` was *not* flagged `degraded` (Section 5.2's own near-identical-edit signal) — the original AI draft is included alongside its final, paired, with an explicit instruction to compare them and carry forward whatever pattern of tone, structure, or word-choice preference the edit reveals, rather than repeating the same issue next time. Episodes with a near-identical draft/final pair carry no editorial signal and are shown as final-only, same as before, to avoid diluting the prompt with pairs that teach nothing. This is prompt-based, not model fine-tuning — fine-tuning was considered and rejected as impractical at this stage (too few real episodes to train on, and it would fight the guidelines-doc-driven design's whole premise that redefining a show's voice is a doc edit, not a code or model change).
- `thinking: {"type": "disabled"}` is required on this call (see Section 1 lessons).

### 5.2 Human Review Step (new, required)
A distinct pipeline stage exists between AI draft and "final": **Script reviewed & saved.** Real-world experience recording trial episodes showed the AI draft consistently needs editing before being voiced — this is expected ongoing workflow, not a temporary trial-phase quirk. The admin UI needs a real script-review screen (full-width editor; a side-by-side draft/final layout was tried and rejected as insufficient for genuine editing — the final version gets full screen width, with the AI draft available behind a collapsed toggle for reference).

**Safeguard**: a similarity/diff check compares the saved final text against the original AI draft. If suspiciously close to identical, show a non-blocking warning badge (e.g., "X% changed" in a caution state) rather than silently proceeding — a legitimate zero-edit day is possible, so this flags for a second look rather than blocking the save.

It is the **reviewed, final** version that gets archived as this show's permanent historical record. The original AI draft is also fed forward, but only for the subset of recent episodes where it differs meaningfully from the final (Section 5.1's editorial-preference learning) — never as the archived/canonical version of the episode itself.

## 6. Publishing Integrations

### 6.1 Captivate
- Shared account login across all shows; unique `show_id` per Show Instance, connected via an explicit "Connect Captivate show" action on the show setup screen (Section 11) — not just a value sitting in the data model with no UI surfacing it.
- Per-episode artwork upload is supported (confirmed directly).
- The real scheduling/immediate-publish field is `date`, format `YYYY-MM-DD HH:mm:ss` (space-separated, not ISO), interpreted in the show's configured account timezone. A past value publishes immediately; a future value schedules. (Three other plausible field names were tried first and silently ignored by Captivate's API before this was found in their actual documentation — do not repeat that guessing pattern for any other undocumented field; check the real docs or a live response first.)
- **Full end-to-end verification**: after creating an episode, re-fetch it by ID and confirm it actually exists with the expected title/date — do not treat the creation call's success response alone as proof of a live, correct result.

### 6.2 Website (WordPress + AIOSEO)
- **Per-episode page auto-published** at episode-publish time (not just a static show hub) — this is the primary SEO/AEO value driver of the website layer.
- **AIOSEO integration via real hooks**, not the plugin's own UI-only path: `aioseo_description` filter and the `aioseo_save_post` action are the confirmed programmatic entry points (AIOSEO stores data in its own structure, not standard post meta — writing there directly will not work).
- **Do not use AIOSEO's own built-in AI title/description generator** — it runs on a separate paid-credits system with no awareness of the show's guidelines or that day's script; our own generation call already has full context and should populate these fields directly.
- **No focus keyphrase field** — explicitly rejected (varies too much per episode, presupposes manual copy-editing that isn't intended).
- **`PodcastEpisode` schema (JSON-LD)** output directly via WordPress's `wp_head` hook — do not assume AIOSEO natively supports this schema type; hand-rolling via `wp_head` works regardless of what the plugin does or doesn't support.
- **Post author = the specific talent who voiced that episode** (not necessarily the show's current default talent) — required for AIOSEO's EEAT schema support to attribute correctly. AIOSEO's own EEAT configuration per talent (in AIOSEO's WordPress user UI) is handled manually at talent onboarding and is **out of scope** for this system beyond ensuring the correct WordPress user is set as post author at publish time.
- **Guidelines content history**: use WordPress's native built-in Revisions system — no separate plugin needed.
- **Cross-show hub page**: a top-level "all our shows" page linking between every live show, for sitewide internal-linking SEO value.
- **URL structure**: subdirectories (`studio-domain.com/shows/{show-slug}/`) are canonical — preserves SEO authority consolidation under one domain, single WordPress install. Subdomains were considered and rejected as the default (only worth the complexity if a show might later spin off to a fully independent domain). **Custom domain mapping** is supported as a future/optional layer for a specific client — DNS/redirect pointing at the canonical subdirectory, not a separate infrastructure buildout.
- **Full end-to-end verification**: after publishing, fetch the live page URL and confirm it actually returns and contains the expected content.

### 6.3 YouTube
Treated as its **own distinct build phase** — a third full publishing platform, not a small addition to the image pipeline.

- **Full native upload (not RSS-import-then-retrofit-thumbnail)**: render a static-image "video" (the 16:9 episode art held for the full audio duration, combined via `ffmpeg`) and upload directly via the YouTube Data API. This was chosen over relying on YouTube's own podcast-RSS auto-import feature specifically because that import's timing is an unpredictable external black box — full native upload gives deterministic control over both timing and thumbnail.
- **Mandatory prerequisite**: the channel must be phone-verified before any programmatic thumbnail-setting is possible (confirmed in Google's own documentation, no exception) — part of new-show onboarding for any show going to YouTube.
- **Per-show connection**: an explicit "Connect YouTube channel" OAuth action on the show setup screen (Section 11), same reasoning as the Captivate connection above — this data must never be schema-only with no UI path to actually set it.
- **SEO-optimized title, description, and tags** are a required, explicit project goal — generated by the same metadata-generation call as the Captivate/AIOSEO fields, following YouTube-specific conventions (first ~125 characters of description are what's visible before truncation; a real generated tag list).
- **Title selection**: the AI generates a single, well-reasoned best title upfront. **No live A/B testing** — YouTube's native "Test & Compare" feature is confirmed Desktop-Studio-only with no API access at all, fundamentally incompatible with unattended automated publishing. Building a custom rotating A/B mechanism via the Analytics API was considered and explicitly not chosen.
- **No literal "optimization score" exists to check against** — confirmed YouTube publishes no official such score (only third-party tools like VidIQ/TubeBuddy compute their own proprietary versions). Instead, build an **internal pre-publish checklist** validating known, public best-practice criteria (title length and keyword presence, description length, tag count, thumbnail spec compliance) — the pipeline does not publish to YouTube until every criterion in this checklist passes.
- **Quota discipline**: use a **single GCP API project/client across every show** — never create separate projects per show to multiply quota. YouTube's API Terms of Service explicitly prohibit this ("sharding"). Request a legitimate quota increase from Google if/when real scale requires it. Default daily quota (10,000 units) allows only a handful of video uploads/day (~1,600 units each) — plan for a quota increase request before this becomes a live constraint, not after.
- **Known unresolved risk, not a blocker**: YouTube's spam/inauthentic-content enforcement has historically targeted patterns of many channels publishing visually/structurally similar templated content at scale. Each show's actual script and voice are genuinely distinct by design, which mitigates this, but it's worth a closer look once enough live channels exist for the pattern to become visible — no specific current policy citation was found to assess this precisely.
- Automated, non-interactive publishing itself is confirmed **not** against YouTube's rules (legitimate open-source bulk-upload tooling exists for exactly this use case).
- **Full end-to-end verification with an inherent delay**: uploaded videos go through a real processing phase before being genuinely live (sometimes several minutes) — this is an external delay outside our control, not a bug. The dashboard should show this step as "in progress" (see Section 8) immediately after upload, with a follow-up check resolving it to verified or failed once processing actually completes.

## 7. Image Pipeline

Three output images per episode, each with its **own distinct, purpose-built compositing frame** — the *frames* are not derived from one another (each is its own template, sized and branded for its own platform's convention: 3000×3000 is the universal podcast-cover-art square, 16:9 is YouTube's own thumbnail convention, 1200×630 is the established Open Graph/social-link-preview convention — three genuinely different platform standards, not an arbitrary split):

| Output | Dimensions | Format | Size cap | Purpose |
|---|---|---|---|---|
| Podcast art | 3000×3000 | JPEG | ≤500KB | Captivate |
| YouTube art | 16:9 (1280×720) | JPEG | ≤1MB | YouTube thumbnail/video |
| Website art | 1200×630 | WebP | — (soft-optimized toward a small filesize regardless, for page-load performance/SEO) | Open Graph / website |

- **One base image per episode, not three.** A single AI-generated base image — not three independently generated images — is cropped to fit each of the three output ratios. Generating three separate images per episode risked the same episode looking like three unrelated pieces of art across Captivate/YouTube/website, which would be confusing to a listener following the show across platforms; one shared base image, cropped, keeps the episode visually recognizable everywhere it appears. The base image is generated at the **widest of the three target ratios** (currently 1200×630's ≈1.91:1) so the other two, narrower outputs are obtainable by a pure inward crop, never by padding or fabricating content at the edges.
- **Frame/template assets**: PNG (needs alpha transparency for the compositing cutout), stored per-show, with a dedicated UI section for uploading/replacing all three independently. (This was initially missing from the show setup mockup and has been added as a required field group.)
- **Base art**: AI-generated per episode, informed by that day's actual stories (same context-aware approach as the metadata generation), then composited into the show's fixed frame. Provider: **Gemini 2.5 Flash Image ("Nano Banana") via Google's Vertex AI / Agent Platform**, using the GCP project/billing relationship already established for this project — no genuinely free production-grade image generation API exists, but real per-image cost at this project's scale is negligible. (Originally specified as Imagen; switched during build after live discovery that Imagen requires a Google-approved allowlist request with no confirmed timeline, while this model — still first-party Google, still a plain serverless API call — was immediately usable on the same project with no such gate.)
- **Optional per-show style treatment**, applied to the base image before cropping or frame compositing: a show may specify a duotone treatment (grayscale conversion, contrast/brightness adjustment, then two brand-color blend layers — shadow tone via multiply blend, highlight tone via screen blend) using that show's own two chosen colors. The technique's parameters (contrast/brightness/blend opacities) are fixed; only the two colors are per-show. Default is no treatment. (First real-world case: Net Gain Edtech's green duotone treatment, specified in a production design reference document with exact colors and blend values.)
- **Compositing implementation**: Python's Pillow library, run as a step in the existing pipeline (not a new platform or language).
- **Graceful fallback (required)**: if AI image generation fails for any reason, each show has a pre-rendered static default branded image (already run through all three frames/formats) that is used automatically instead. **Publishing must never be blocked by an image failure.** This state shows as the Amber/"completed, degraded" dashboard status, not a failure.
- **Human review step**, mirroring Section 5.2's script review: the rendered images are surfaced for a human to look at close to when they're generated (shortly after audio upload, since image generation is not deferred to publish time — see Section 8.3) — both to the admin and to the talent assigned to that show — with a manual regenerate control available if the result doesn't look right. Images render as soon as audio is received; a human can review and, if needed, regenerate before publish time, rather than only discovering a bad result after the fact.
- Frame and style-treatment changes apply prospectively only (see Section 4.1).

## 8. Episode Queue, Manual Triggers & Publish Timing

### 8.1 Audio Intake & Finalization
- Fully WordPress-native upload surface — no Google Drive involvement.
- **Upload triggers finalization directly** — not discovered later by a periodic polling tick.
- **Visible countdown, not a silent timer**: immediately after a successful upload, the UI shows a real, ticking countdown (default 90 seconds, tunable) with two explicit controls:
  - **Abort**: stops the pending finalization and holds this episode as "awaiting replacement" until a new file is uploaded, which starts a fresh countdown of its own.
  - **Publish now**: skips the remaining wait — see 8.2 for what this actually triggers.
  - Neither button receives primary/accent visual styling — the actual default path is doing nothing and letting the countdown finish naturally.
  - **Access**: talent-only control, scoped to their own upload. No admin override needed.
- **Amended during the build (supersedes the original "proceed promptly" language below this note):** finalization does **not** trigger metadata generation immediately. Metadata (and any other publish-facing generation besides images) is deliberately deferred until close to the show's actual publish moment — generating it immediately would be wasted work whenever a queued episode is later aborted and replaced before publishing (8.2 allows exactly this, at any point up to the publish moment). **Image generation is the one exception**: since it's independently, manually triggerable at any time (8.3) regardless of timing, there's no similar waste to avoid. Finalization and publication remain two separate events, not one — this amendment only changes *when* the in-between generation work happens, not that separation.

### 8.2 The Local Queue — finalization is not publication
A finalized episode (script locked, audio locked — metadata and images generated later, close to publish time, per the amendment in 8.1) is held as a **queued episode inside our own system** — nothing has been pushed to Captivate, the website, or YouTube yet. It sits in this queue until its show's configured publish moment arrives. This is a deliberate architectural choice, not just a scheduling delay: an episode that hasn't been pushed anywhere external is trivially easy to inspect, edit, or kill, which a "publish immediately then fix it after the fact across three platforms" design would not allow.

- **Per-show publish configuration**, entirely independent of the show's recording target time/timezone (Section 11):
  - **Publish mode**: `Immediately once finalized` or `At a scheduled time`.
  - **Publish time** + **Publish timezone** (used when mode is scheduled). Example: Net Gain Investor records Pacific afternoons but publishes 7:00 AM **Eastern** the next day — recording time/timezone and publish time/timezone are genuinely independent settings, not the same field reused.
  - Mechanically: for Captivate, this is computing the target moment and formatting it in the account's configured timezone as the `date` field's future value (Section 6.1) — Captivate's own scheduling holds it from there. For the website and YouTube, the tick loop simply withholds the publish call until the target time arrives.
- **"Publish now" is an override for both waits** — the finalization countdown (8.1) and any scheduled-publish wait (8.2) — for genuinely time-sensitive days. It is the same button/concept in both places, not two different mechanisms.
- **Abort is available at any point an episode sits in the queue**, not only during the initial post-upload countdown. A queued episode can be canceled at any time before its scheduled publish moment — minutes or hours out — from the queue/dashboard view, with nothing to undo externally since nothing has been pushed yet.
- **Editing a queued episode must be obvious, not buried.** A queued episode's detail view surfaces every deliverable — script text, audio file, rendered images, generated metadata — each with a direct, visible action to replace or regenerate it in place (the manual per-step triggers in 8.3), without needing to abort and restart the whole episode to fix one piece.
- A future "replace already-published audio after the fact" capability (i.e., after the queue has already emptied to all three platforms) was discussed as a possible later addition but is **not** part of this build — meaningfully heavier to implement correctly across three platforms once they're each independently live, and the pre-publish queue is expected to cover the realistic case.

### 8.3 Manual Step Triggers (idempotent against scheduled triggers)
- **Script generation**, **image generation**, and **Captivate publish** must each be independently, manually triggerable from the admin UI, per show — not only reachable as part of an automatic chain.
- **Manual and scheduled triggers for the same step are interchangeable, never additive** (general principle, same category as Section 9's publish-target independence): whichever one completes a step for a show on a given day marks that step done, and the tick loop checks this state before attempting its own scheduled version of the same step, skipping silently if already satisfied. Triggering script generation by hand at 10 AM means the show's normal automated slot later that day sees the step already complete and does not regenerate or overwrite it.
- **Prerequisite-aware controls**: a manual trigger for a step whose prerequisite hasn't completed (e.g., Captivate publish before that day's metadata and images both exist) should be visibly disabled in the UI, not silently fail against missing input. (Amended during the build: image generation and metadata generation are siblings, each gated only on audio being received, not on each other — image generation must remain triggerable independent of metadata's timing, since metadata generation is deliberately deferred close to publish time per the 8.1 amendment, while images are not.)

## 9. Reliability & Failure Handling

- **Publish-target independence (required architecture constraint)**: after the shared upstream steps (script review, audio received, metadata generated, images rendered) that every publish target genuinely depends on, **Captivate, website, and YouTube publishing must execute as three fully independent operations** — a failure in one must never prevent attempts at the other two. (An early dashboard mockup incorrectly showed this coupled and was corrected.)
- **Failure email alerting**, per show, per failure — not just a log file nobody is watching.
- **Missed-upload alerting**: if no recording has been received by a show's cutoff time, send an alert (to the studio and/or the talent) — same urgency treatment as an outright pipeline failure.
- **Standardized retry-with-backoff wrapper**, used consistently across every third-party API call (Anthropic, Captivate, YouTube) — not handled ad hoc per integration. Real precedent for why this matters: a live cron log during the original single-show build showed two genuine, transient Captivate 503 errors in one morning, both recovered automatically on the next attempt a few minutes later.
- **Rate-limit awareness at real multi-show, concurrent-execution scale** — both sustained daily volume *and* burst/simultaneous-timing load (several shows legitimately hitting the same provider's API in the same second is a different failure mode than steady load spread across a morning).
- **Backup strategy** required now that WordPress, media, and code all consolidate onto one Canspace account, rather than being naturally spread across Drive's redundant cloud storage as in the original single-show design. Needs a deliberate decision at build time, not a discovered gap later.

## 10. Operations Dashboard

An LED/lamp-style status grid: rows = shows, columns = the pipeline steps below, one row per day, date-navigable.

**Pipeline steps (8, in order):**
1. Script generated
2. Script reviewed & saved
3. Audio received
4. Metadata generated (Captivate notes, AIOSEO fields, YouTube title/description/tags)
5. Images rendered
6. Captivate published
7. Website published
8. YouTube published

**Status states (five, each with one consistent meaning — do not reuse a color for two different situations):**
- **Green**: fully, end-to-end verified — confirmed by re-querying the actual destination system, not just trusting that our own API call returned success. This applies to *every* step, including confirming the episode genuinely appears on Captivate and on YouTube.
- **Amber (solid)**: completed, but degraded — e.g., the image fallback was used, or the final script was suspiciously close to the AI draft. Never shown as red; this is a working safety net, not a failure, and conflating the two would dilute what red means.
- **Blue (pulsing/animated)**: genuinely in progress, not yet resolved — e.g., YouTube video still processing after upload, or an audio upload's countdown window still running. Resolves to green or red once settled. Distinct in both color and motion from Amber, since it represents a different kind of state (not done yet, vs. done-but-flagged).
- **Red**: genuine failure.
- **Gray**: step not yet reached.
- **Queued (distinct visual treatment, not a sixth color)**: a finalized episode in scheduled-publish mode (Section 8.2) waiting for its configured publish time shows its Captivate/website/YouTube columns as visibly *queued* rather than plain Gray or false-progress Blue — this is a deliberate, expected wait, not an unstarted step or active work. Exact visual treatment (e.g., an outlined/hollow variant of Gray) is a build-time detail; the requirement is that "waiting on purpose" reads differently from "hasn't started" or "actively running."

**Interaction requirements:**
- Every non-green state has a **mouseover tooltip** with plain-language status plus specific, concrete troubleshooting guidance — seeded from real lessons learned during this project's build (e.g., the Captivate-failure tooltip should mention checking the logged raw response body first, since that is what previously revealed an undocumented field name), not generic "check the logs" text.
- **Every LED that references a durable artifact links directly to that artifact** — script draft, final reviewed script, the master audio file as uploaded, the three rendered images, and the three live published pages (opens in a normal new browser tab; forcing a private/incognito window is not something a webpage can control — that remains a manual browser action for anyone who specifically wants to view a page in a logged-out state, most relevant for the website link since the person will typically be logged into WordPress admin in the same browser).
- The dashboard is a **real historical record**, backed by the persisted Episode data model (Section 4), not just today's in-memory state — must support navigating to or paginating through previous days to review past scripts, links, and the master audio file.
- **Mobile-readable, required.** The wide multi-column grid concept needs a genuinely different narrow-viewport layout (e.g., a stacked card per show, expandable for full step detail) — not simply the same grid with horizontal scrolling.
- The dashboard header reflects the actual current day of week and date.

## 11. Admin UI — Show Setup Screen

Confirmed field set, each with **considerable inline guide/help text** — every field must be unambiguous about what's expected, with no exceptions across any admin form in the system:

- Show name
- Vertical template (seeds starting guidelines; fully editable afterward)
- Website subdirectory slug
- Recording days
- Target time (when the script needs to be ready for talent to record)
- **Timezone** (explicit, separate field — decoupled from wherever the talent physically resides; anchors to the show's own audience/schedule, not the talent's location)
- **Publish mode**: Immediately once finalized / At a scheduled time (Section 8.2)
- **Publish time** + **Publish timezone** (shown when mode is scheduled) — independent fields from Target time/Timezone above; a show can record in one timezone and publish in another (e.g., Pacific afternoon recording, 7:00 AM Eastern publish the next day)
- Recent-script lookback window (days)
- Primary talent (select)
- Editorial guidelines — a link/button out to the full WordPress content-editor page, **not** an inline textarea (these documents run long and need real HTML formatting)
- Three branding/compositing frame uploads (square / 16:9 / 1200×630), each independently replaceable
- **Connect Captivate show** — explicit connection action, not a bare ID field (Section 6.1)
- **Connect YouTube channel** — explicit OAuth connection action (Section 6.3)
- **Show status** (field renamed from "Status"): Active / Paused / Concluded
- **Save changes** button (renamed from "Save show")

## 12. Roles & Access

- **Admin** (the studio operator): sees and manages all shows.
- **Talent**: sees and accesses only their own assigned show(s), plus any show(s) they are currently covering as a substitute for a specific date range.

## 13. Test / Staging Environment

A fully isolated, end-to-end test environment, not a partial simulation:
- A dedicated test Show Instance.
- A dedicated test Captivate podcast.
- A website presence excluded from site navigation and marked no-follow for crawlers.
- A private/unpublicized YouTube channel or playlist.
- **No real public surface is ever exposed** by test activity.
- **Hidden from the daily dashboard by default**, behind a collapsed disclosure control (a "turning triangle" expand/collapse widget) — visible only when deliberately opened, so it never clutters the daily operational view.

## 14. Build Approach

Split by task type, not handled by a single tool:
- **Claude Code**: the actual software engineering — the WordPress plugin, the Python pipeline scripts, the database schema. A proper local project, in a **new, dedicated repository named `net-gain`** (deliberately separate from the existing `net-gain-automation` repo, which keeps running the old single-show pipeline untouched until its own future decommission — no shared history, no risk of the new build interfering with what's still live).
- **Chat interface, with live tool access, does every actual deployment** — this is the confirmed loop, expected to run through many iterations: Claude Code produces or updates code locally, hands it off, and the chat session installs it on the real infrastructure. Two distinct deployment surfaces, two different tools on the chat side:
  - **WordPress plugin** → installed via WPVibe (already connected to `netgain.news`).
  - **Python pipeline scripts on Canspace** → deployed via cPanel access (browser control or File Manager, same approach used throughout the original single-show build).
- **WordPress installation itself**: already done — the account owner provisioned the instance and connected it via WPVibe's own authorization flow, consistent with the project-wide principle that the account owner always holds root credentials on every system from the first moment.

## 15. Explicitly Open Items (not resolved in this spec)

- Real compliance/legal review for any regulated vertical (e.g., financial) — required before launch, intentionally outside this spec's scope.
- Exact process/timing for requesting a YouTube API quota increase once real scale requires it.
- Precise current YouTube policy language on templated-content-at-scale enforcement, worth a closer look once multiple live channels exist.
- Backup strategy for the consolidated Canspace-hosted stack (Section 9) — flagged as required, not yet designed.

---

*This document reflects a full design conversation and should be treated as the authoritative source of decisions for the initial build. Where this spec is silent on an implementation detail, prefer the general principles stated in Section 4.1 (prospective-only changes) and Section 9 (publish-target independence, verification-by-re-query) as tie-breakers.*
