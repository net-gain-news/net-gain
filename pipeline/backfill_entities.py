"""
Tags every published episode that has no topic tags yet (entities.py), oldest first so each episode sees the names
earlier ones already settled on. Safe to re-run: episodes that already have tags are skipped unless --force.

  python3 backfill_entities.py SHOW_ID            # preview: prints what it would store
  python3 backfill_entities.py SHOW_ID --apply    # stores the tags
  python3 backfill_entities.py SHOW_ID --apply --force   # re-tag even tagged episodes
"""

import argparse
import logging
import sys

import anthropic

from anthropic_client import generate as anthropic_generate
from config import load_config
from entities import extract_entities, known_entity_names
from wp_client import WPClient


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("show_id", type=int)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    config = load_config()
    wp = WPClient(config["WP_BASE_URL"], config["WP_SERVICE_USERNAME"], config["WP_SERVICE_APP_PASSWORD"])
    client = anthropic.Anthropic(api_key=config["ANTHROPIC_API_KEY"], timeout=600.0)
    show = next(s for s in wp.get_tick_context() if s["id"] == args.show_id)

    episodes = wp.list_episodes_for_show(args.show_id)
    episodes = [e for e in episodes if (e.get("meta") or {}).get("ng_website_post_id") and (e.get("meta") or {}).get("ng_script_final")]
    episodes.sort(key=lambda e: (e.get("meta") or {}).get("ng_episode_date") or "")
    stored = {e["id"]: (e.get("meta") or {}).get("ng_entities") or [] for e in episodes}

    failures = 0
    for episode in episodes:
        meta = episode["meta"]
        if stored[episode["id"]] and not args.force:
            continue
        known = known_entity_names([{"id": i, "meta": {"ng_entities": v}} for i, v in stored.items() if i != episode["id"]])
        try:
            entities = extract_entities(lambda **kw: anthropic_generate(client, **kw), show["name"],
                                        meta.get("ng_episode_date", ""), meta["ng_script_final"], known)
        except Exception as exc:
            failures += 1
            print(f"{meta.get('ng_episode_date')}  episode {episode['id']}: FAILED ({exc})")
            continue
        stored[episode["id"]] = entities
        print(f"{meta.get('ng_episode_date')}  episode {episode['id']}:")
        for e in entities:
            print(f"    [{e['kind']}] {e['name']} - {e['note']}")
        if args.apply:
            wp.update_episode_meta(episode["id"], {"ng_entities": entities})
    print("\nstored" if args.apply else "\nPREVIEW ONLY (nothing stored; add --apply)", f"- {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
