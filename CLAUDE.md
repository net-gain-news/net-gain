# Net Gain — Multi-Tenant Newscast Studio

You are building this project. **Read `SPEC.md` in this same directory before writing any code** — it is the full, authoritative design document from an extensive planning conversation and covers the business model, data model, every publishing integration, the image pipeline, the operations dashboard, and the admin UI in detail. This file is the orientation layer on top of it: the connecting-tissue decisions the spec describes the *result* of but doesn't spell out mechanically, plus practical setup information.

## What this is, in one paragraph

A system that produces branded, sponsor-underwritten daily newscasts for multiple simultaneous "vertical" shows (financial advisors, real estate, ed-tech, etc.), each independently scripted (via Claude), voiced, and published to Captivate, a WordPress-hosted episode page, and YouTube. It replaces an earlier single-show pipeline (still running, untouched, elsewhere — see "What NOT to touch" below) with a real multi-tenant admin system: add a new client show through a WordPress admin screen, not by editing code or cron jobs.

## The one architectural decision this project needs that the spec doesn't fully mechanize

**Python and WordPress are two separate runtimes on the same Canspace server — they don't share memory or call each other directly. Here's how they're meant to talk:**

- **Python → WordPress (reading/writing data)**: via WordPress's REST API. The plugin registers custom routes (or uses standard ones against the Episode/Show custom post types Seriously Simple Podcasting and your own plugin code provide) for show config and episode records. Python authenticates with a WordPress **Application Password**, not a shared database connection — keep the two systems loosely coupled.
- **WordPress → Python (manual "run now" triggers, Section 8.3 of the spec)**: WordPress does **not** invoke a Python process directly. Clicking "run now" for script generation, image generation, or Captivate publish should write a pending-action record via the REST API — a flag the *same* tick-loop cron job (Section 3.1) checks on its next pass, the identical code path used for scheduled execution. This is deliberate, not a shortcut: one execution path for both manual and scheduled triggers is what makes the idempotent "whichever happens first wins, the other is skipped" rule in Section 8.3 straightforward to implement correctly. Do not build a second, separate "instant trigger" pathway alongside the tick loop — it would need to duplicate all of the same completion-checking logic.
- **The tick loop itself** runs frequently (every few minutes is reasonable — this is an implementation detail, not something the spec pins to an exact number) and, each pass, checks every `Active` show for: any due scheduled step, any pending manual-trigger flag, and any queued episode (Section 8.2) whose configured publish time has arrived.

## Deployment — read this before assuming you can ship anything yourself

**You do not have deployment access to the live site or server, and you should not attempt to.** When code is ready to test or ship:
- **WordPress plugin changes** are installed by a separate Claude session with direct WPVibe access to `netgain.news`. Hand off the plugin code/changes; that session performs the actual install.
- **Python pipeline script changes** on Canspace are deployed the same way, via that session's cPanel access.
- Expect **many iterations** through this loop — this was explicitly planned for, not a sign something's going wrong. Package changes in reviewable chunks rather than one enormous diff at the end.

## Repository

New, dedicated repo: **`net-gain-news/net-gain`**. Deliberately separate from the existing `net-gain-automation` repo.

### What NOT to touch
`net-gain-automation` (the original single-show pipeline) is still live and running on its own schedule, publishing the original show's automation. It is being left completely alone until a deliberate future decommission. Nothing in this project should read from, write to, or depend on that repo, its Google Drive documents, or its GitHub Actions/Canspace cron configuration. Full architectural independence — the only things genuinely shared are the Anthropic API key and the Captivate account login (see Credentials below), and even those are used with entirely separate show/episode identities.

## Credentials this system needs (names only — actual values are provided by the human operator when each is needed, never hardcoded or requested from you)

| Env var / secret | Purpose | Source |
|---|---|---|
| `ANTHROPIC_API_KEY` | Script + metadata generation | Reused from the existing single-show project |
| `CAPTIVATE_USER_ID`, `CAPTIVATE_API_TOKEN` | Captivate account API access (shared across all shows) | Reused from the existing single-show project |
| `GOOGLE_CLOUD_PROJECT` credentials (Vertex AI) | AI image generation (Imagen) | New, dedicated GCP project — not the old Drive-oriented one |
| YouTube OAuth client ID/secret + per-show refresh tokens | Native video upload, thumbnail-setting | Same new GCP project as Vertex AI (required — YouTube's API terms prohibit separate projects per show, "sharding") |
| WordPress Application Password | Python → WordPress REST API auth | Generated per the mechanism above, scoped to the plugin's service account/user |
| Git deploy credential | Pulling this repo onto Canspace | Set up when first needed, not gathered in advance |

## First real show — seed data, not a hypothetical

The first live Show Instance is **Net Gain Edtech**. Concrete, already-real values worth using directly rather than placeholder data when building and testing the Show/Episode data model:

- Show name: `Net Gain Edtech`
- Talent (primary, and initial post author / EEAT profile): Dallas Kachan
- Captivate show ID: `f40bbab2-a721-4bec-9de7-aa82b5488060`
- No historical episodes to migrate — this show starts with zero episodes in its archive, which is a genuinely valid and expected state, not an edge case to special-case around.
- Early episodes may be produced and published **manually**, outside this system entirely, while the build is in progress — this project does not need to accommodate or import that manual activity; it's a separate bridge process with no dependency in either direction.

## Suggested internal build order

The business asked for this delivered as one complete system rather than phased feature rollout — but a sensible internal implementation sequence still matters for a build this size:

1. Data model / schema (Vertical, Show, Talent, Episode) as WordPress custom post types + the plugin's REST routes, per Section 4 of the spec.
2. Show setup admin screen (Section 11) — get show creation/editing working end-to-end before anything depends on show data existing.
3. Script generation pipeline (Section 5) talking to a real show via the REST API.
4. The review/finalization/queue mechanics (Section 8) — this is a substantial and easy-to-underbuild piece; don't treat it as an afterthought bolted onto audio upload.
5. Captivate publishing (Section 6.1) — the most well-understood integration, given the extensive real-world debugging already captured in Section 1's "lessons carried forward."
6. Website publishing + AIOSEO + schema (Section 6.2).
7. The operations dashboard (Section 10) — much easier to build once real Episode records already exist from steps 3–6 to display.
8. Image pipeline (Section 7).
9. YouTube (Section 6.3) — explicitly its own phase per the spec; build it last, not in parallel with the others.

## When you're blocked on something only the human operator can provide

Say so plainly and specifically (which credential, which manual step, which decision) rather than stubbing around it silently. Given how much of this project's history involved discovering undocumented third-party API behavior the hard way (Section 1), the same discipline applies here: verify against real documentation or a live response before building on an assumption, and prefer failing loudly and specifically over guessing quietly.
