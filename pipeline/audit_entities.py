"""
Audits the stored topic tags against the scripts (read-only): for every place and organization the scripts name, how many
episodes mention it and how many carry its tag (a place counts when the tag or any child place carries it); the tag-count
histogram; and the topic tags with no supporting words in the script. Run before and after a change to entities.py.

  python3 audit_entities.py SHOW_ID
"""

import collections
import re
import sys

import gazetteer
from config import load_config
from entities import slugify, spoken_script
from wp_client import WPClient

ORGS = ["Frontline", "PowerSchool", "Google", "Microsoft", "OpenAI", "EDUCAUSE", "1EdTech", "Federal Communications Commission|FCC",
        "Instructure|Canvas", "Anthropic", "Department of Education", "FBI", "OASBO", "CoSN", "ISTE", "Tribal Group", "Duolingo", "Coursera"]

DEAL_WORDS = re.compile(r"acqui|merger|takeover|buyout|private equity|sale to|bid\b", re.I)


def tagged_slugs(tags):
    """Every slug an episode's tags cover, including the parents they roll up to."""
    parents = {t["slug"]: t.get("parent") for t in tags}
    covered = set()
    for t in tags:
        slug = t["slug"]
        while slug and slug not in covered:
            covered.add(slug)
            slug = parents.get(slug) or ""
    return covered


def main(argv):
    wp = WPClient(*(lambda c: (c["WP_BASE_URL"], c["WP_SERVICE_USERNAME"], c["WP_SERVICE_APP_PASSWORD"]))(load_config()))
    episodes = [e for e in wp.list_episodes_for_show(int(argv[0])) if (e.get("meta") or {}).get("ng_script_final")]
    rows = [((e["meta"].get("ng_episode_date") or ""), spoken_script(e["meta"]["ng_script_final"]), e["meta"].get("ng_entities") or []) for e in episodes]
    rows.sort()
    print(f"{len(rows)} episodes; tags per episode: {dict(sorted(collections.Counter(len(t) for _d, _b, t in rows).items()))}")
    print(f"episodes with no tags: {sum(1 for _d, _b, t in rows if not t)}")

    print("\nPLACES (mentioned in / covered by a tag):")
    names = [p[0] for p in gazetteer.places()] + list(gazetteer.PLACE_ALIASES)
    results = []
    for place in names:
        canonical = gazetteer.PLACE_ALIASES.get(place, place)
        mentions = [t for _d, b, t in rows if re.search(r"(?<![A-Za-z])" + re.escape(place) + r"(?![A-Za-z])", b)]
        if len(mentions) >= 3:
            results.append((len(mentions), sum(1 for t in mentions if slugify(canonical) in tagged_slugs(t)), canonical))
    for m, t, p in sorted(set(results), reverse=True):
        print(f"  {p:22} {m:3} / {t:3}{'   <-- gap' if t < m else ''}")

    print("\nORGANIZATIONS (mentioned in / tagged):")
    for org in ORGS:
        key = slugify(org.split("|")[0])
        mentions = [t for _d, b, t in rows if re.search(org, b)]
        if mentions:
            tagged = sum(1 for t in mentions if any(key in x["slug"] or x["slug"] in key for x in t))
            print(f"  {org:40} {len(mentions):3} / {tagged:3}")

    print("\nTOPIC TAGS:")
    counts = collections.Counter(x["name"] for _d, _b, t in rows for x in t if x["kind"] == "topic")
    for name, n in counts.most_common():
        print(f"  {n:3}  {name}")
    merger = "edtech-mergers-and-acquisitions"
    print("\nM&A tagged without deal words in the script:",
          [d for d, b, t in rows if any(x["slug"] == merger for x in t) and not DEAL_WORDS.search(b)])
    print("deal words but not tagged (check by hand):",
          [d for d, b, t in rows if len(DEAL_WORDS.findall(b)) >= 3 and not any(x["slug"] == merger for x in t)])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
