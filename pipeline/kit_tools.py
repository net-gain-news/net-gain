"""
Operator tools for the Kit emails. Nothing here sends an email: previews are saved as unsent drafts in Kit.

    python kit_tools.py check [show_id]            check the show's Kit settings against the real Kit account
    python kit_tools.py daily-draft [show_id]      an unsent draft of the newest episode's daily email
    python kit_tools.py weekly-draft [show_id]     an unsent draft of the weekly roundup built from the newest episodes
    python kit_tools.py delete-draft BROADCAST_ID  delete an unsent draft (refuses anything that is scheduled or sent)

A draft appears in Kit under Broadcasts; open it there to see the finished email, and delete it when done.
"""
import sys
from datetime import datetime, timezone

import kit_email
from config import load_config
from kit_client import KitClient
from wp_client import WPClient


def _pick_show(shows, show_id):
    if show_id:
        matches = [s for s in shows if str(s["id"]) == str(show_id)]
    else:
        matches = [s for s in shows if (s.get("kit") or {}).get("daily_tag_id")] or shows
    if not matches:
        raise SystemExit("No matching active show.")
    return matches[0]


def main(argv):
    if len(argv) < 2 or argv[1] not in ("check", "daily-draft", "weekly-draft", "delete-draft"):
        print(__doc__)
        return 2
    config = load_config()
    client = KitClient(config["KIT_API_KEY"])
    command = argv[1]

    if command == "delete-draft":
        broadcast = client.get_broadcast(argv[2])
        if broadcast.get("status") != "draft":
            print(f"Refusing: broadcast {argv[2]} is {broadcast.get('status')!r}, not an unsent draft.")
            return 1
        client.delete_broadcast(argv[2])
        print(f"Deleted draft {argv[2]}.")
        return 0

    wp = WPClient(config["WP_BASE_URL"], config["WP_SERVICE_USERNAME"], config["WP_SERVICE_APP_PASSWORD"])
    show = _pick_show(wp.get_tick_context(), argv[2] if len(argv) > 2 else None)
    kit = show.get("kit") or {}
    now = datetime.now(timezone.utc)
    print(f"Show: {show['name']} (id {show['id']}); Kit sending is {'ON' if kit.get('enabled') else 'off'}.")

    if command == "check":
        account = client.get_account()
        plan = (account.get("account") or {}).get("plan") or {}
        print(f"Kit account: {(account.get('account') or {}).get('name')}, plan {plan.get('plan_type')}, subscriber limit {plan.get('subscriber_limit')}.")
        problems = kit_email.settings_problems(kit, client.list_tags(), client.list_templates())
        for problem in problems:
            print("PROBLEM:", problem)
        print("Settings look usable." if not problems else f"{len(problems)} problem(s).")
        return 1 if problems else 0

    problem = kit_email.check_daily_settings(kit) if command == "daily-draft" else kit_email.check_weekly_settings(kit)
    if problem:
        print("Cannot build a preview:", problem or "the weekly roundup is switched off (no weekly day set).")
        return 1
    items = kit_email.fetch_feed(kit["feed_url"], now)
    if not items:
        print("The email feed has no episodes.")
        return 1

    if command == "daily-draft":
        item = items[0]
        payload = kit_email.daily_payload(kit, show["name"], {"id": 0, "meta": {}}, item, now)
        payload["description"] = f"PREVIEW {payload['description'].replace('[ng-ep-0]', '').strip()} (unsent draft)"
    else:
        slot, _ = kit_email.weekly_slots(kit, now)
        payload = kit_email.weekly_payload(kit, show, items, slot, now)
        payload["description"] = f"PREVIEW {show['name']} weekly (unsent draft, newest {len(items)} episodes)"
    payload["send_at"] = None           # a draft: nothing is sent
    broadcast = client.create_broadcast(**payload)
    print(f"Unsent draft created: broadcast {broadcast.get('id')}, status {broadcast.get('status')}. Open it in Kit > Broadcasts.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
