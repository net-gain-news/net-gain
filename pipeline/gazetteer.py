"""
Names the topic tagger looks for in every script, whether or not the model tagged them (entities.py).

The model decides what a story is about; this list is the safety net for the names that are always worth a tag when a
script says them: every U.S. state, Canadian province and territory, and the countries that turn up in education news.
A hit is only a CANDIDATE - the ambiguous ones (Washington, Georgia, Virginia, "New York Times") are confirmed by a
second, cheap model call before they become tags.

The home country (the United States) is never tagged: it would be on every episode and say nothing.
"""

US_STATES = (
    "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho Illinois "
    "Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi Missouri "
    "Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah Vermont Virginia Washington "
    "Wisconsin Wyoming"
).split() + [
    "New York", "New Jersey", "New Mexico", "New Hampshire", "North Carolina", "South Carolina",
    "North Dakota", "South Dakota", "West Virginia", "Rhode Island", "District of Columbia",
]

CANADIAN_REGIONS = [
    "British Columbia", "Alberta", "Saskatchewan", "Manitoba", "Ontario", "Quebec", "New Brunswick",
    "Nova Scotia", "Prince Edward Island", "Newfoundland and Labrador", "Yukon", "Northwest Territories", "Nunavut",
]

COUNTRIES = [
    "Canada", "United Kingdom", "Australia", "New Zealand", "Ireland", "India", "China", "Japan", "South Korea",
    "Singapore", "Brazil", "Mexico", "Chile", "Colombia", "Argentina", "Egypt", "Jordan", "Saudi Arabia",
    "United Arab Emirates", "Nigeria", "Kenya", "South Africa", "Germany", "France", "Spain", "Italy",
    "Netherlands", "Sweden", "Norway", "Finland", "Denmark", "Estonia", "Poland", "Ukraine", "Israel", "Turkey",
    "Philippines", "Indonesia", "Vietnam", "Pakistan", "Bangladesh", "Hong Kong", "Taiwan",
]

# Spoken forms that mean a listed name. The key is what the script says; the value is the canonical name.
PLACE_ALIASES = {
    "B.C.": "British Columbia",
    "U.K.": "United Kingdom",
    "Britain": "United Kingdom",
    "England": "United Kingdom",
    "Scotland": "United Kingdom",
    "Wales": "United Kingdom",
    "D.C.": "District of Columbia",
}

ORG_ALIASES = {
    "FCC": "Federal Communications Commission",
    "ETS": "Educational Testing Service",
    "OASBO": "OASBO",
    "CoSN": "CoSN",
    "ISTE": "ISTE",
    "FBI": "FBI",
    "GAO": "Government Accountability Office",
    "U.S. Department of Education": "U.S. Department of Education",
    "Department of Education": "U.S. Department of Education",
    "Education Department": "U.S. Department of Education",
}

# Two spellings that are one entity: the page address of the left-hand name moves to the right-hand name, so one organization
# never gets two topic pages. (OASBO is how the script says it; the model sometimes expands it.)
CANONICAL_NAMES = {
    "ontario-association-of-school-business-officials": "OASBO",
    "association-of-school-business-officials-international": "OASBO",
}

# Never tagged: the home country says nothing, the sponsor must not get editorial pages on a sponsored show, and the show's
# own name and index are not news subjects.
NEVER_TAG = {"united-states", "usa", "us", "america", "edsby", "net-gain-edtech", "net-gain-edtech-index", "net-gain-news"}


def places():
    """[(name, kind, parent_name_or_None, level)] for every gazetteer place."""
    out = [(name, "place", None, "region") for name in US_STATES]
    out += [(name, "place", "Canada", "region") for name in CANADIAN_REGIONS]
    out += [(name, "place", None, "country") for name in COUNTRIES]
    return out


def place_parent(name):
    """The parent a gazetteer place sits under (Canada for provinces), or None."""
    for place, _kind, parent, _level in places():
        if place == name:
            return parent
    return None


def place_level(name):
    for place, _kind, _parent, level in places():
        if place == name:
            return level
    return "local"
