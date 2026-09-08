# Net Gain Studio — Python pipeline

Phase 3 of the Net Gain multi-tenant newscast studio build — see `../SPEC.md` and `../CLAUDE.md`. This is the script-generation pipeline: reads a Show's config and recent history over the `net-gain-studio` plugin's REST API (Phase 1), calls Claude to draft today's script, writes it back, and marks the `script_generated` dashboard step.

## Setup

```bash
cd pipeline
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real values; never commit .env
```

On Canspace, `.env` isn't used in production — set the same variables via cPanel's "Setup Python App" tool (Spec Section 3.1), and cron invokes `venv/bin/python tick.py` directly as a CLI process, not through a web request.

## Running

```bash
python tick.py
```

Checks every Active show for a due or manually-triggered script generation, processes each independently (one show's failure never stops the others), and exits. Intended to run frequently from a single cron entry — this is the "tick loop" CLAUDE.md's architecture note describes.

## Two deliberate departures from SPEC.md Section 1

`anthropic_client.py`'s docstring explains both in full: `pause_turn` is resumed per current Anthropic documentation (no synthetic "Continue" user turn — the spec's note describes a different, standard tool-continuation pattern), and thinking is `adaptive` + `effort: low` rather than `disabled`, to avoid a documented failure mode where disabled thinking on a tool-using call can make the model write a fake tool call into visible text instead of really invoking it.

## Testing

```bash
python -m unittest discover -s tests
```

Pure-logic tests only (prompt construction, HTML stripping, lookback filtering, due-date computation) — no network calls, no API key needed. What these tests *can't* cover: an actual live call to Claude or to a real WordPress instance. See `../PHASE_3_HANDOFF.md` for the first real-world run checklist.

## Deliberately not built yet

- Due-checking for any step besides script generation (finalization, queue, publish) — Phase 4 extends `tick.py`'s loop.
- Full failure-alerting policy — `notify.py` is a minimal, honest SMTP hook, not the real subsystem from Section 9.
- Rate-limit handling at genuine multi-show concurrent scale — shows are processed sequentially within one tick for now.
