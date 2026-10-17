"""
Search-result length rules, as AIOSEO's page analysis scores them (read from AIOSEO Pro 5.0.3's own code,
2026-10-16, and checked against a real browser):

- SEO title ("Page title width"): green when the title's rendered width is 400-600 px, measured as
  canvas.measureText at "20px Arial". Width, not characters - "WWW" and "iii" are very different.
- Meta description: green when it is 121-160 characters (120 or fewer is "too short", over 160 "too long").

The model is told the targets and every generated value is checked here, with a margin inside each edge so a
different browser's kerning cannot tip a value into the red.

ARIAL_UNITS are Arial's advance widths in 2048-per-em units. Summing them without kerning lands within about
4 px of the browser's figure (always a touch high), which the margin absorbs. A character not in the table is
priced as a wide "M" so an unusual symbol can only make the check stricter.
"""

# AIOSEO's own edges
AIOSEO_TITLE_PX_MIN = 400
AIOSEO_TITLE_PX_MAX = 600
AIOSEO_DESC_CHARS_MIN = 121
AIOSEO_DESC_CHARS_MAX = 160

# What we generate to: inside the edges, with room for font differences.
TITLE_PX_TARGET_MIN = 430
TITLE_PX_TARGET_MAX = 580
DESC_CHARS_TARGET_MIN = 130
DESC_CHARS_TARGET_MAX = 156

ARIAL_UNITS = {
    " ": 569,
    "!": 569,
    "\"": 727,
    "#": 1139,
    "$": 1139,
    "%": 1821,
    "&": 1366,
    "'": 391,
    "(": 682,
    ")": 682,
    "*": 797,
    "+": 1196,
    ",": 569,
    "-": 682,
    ".": 569,
    "/": 569,
    "0": 1139,
    "1": 1139,
    "2": 1139,
    "3": 1139,
    "4": 1139,
    "5": 1139,
    "6": 1139,
    "7": 1139,
    "8": 1139,
    "9": 1139,
    ":": 569,
    ";": 569,
    "<": 1196,
    "=": 1196,
    ">": 1196,
    "?": 1139,
    "@": 2079,
    "A": 1366,
    "B": 1366,
    "C": 1479,
    "D": 1479,
    "E": 1366,
    "F": 1251,
    "G": 1593,
    "H": 1479,
    "I": 569,
    "J": 1024,
    "K": 1366,
    "L": 1139,
    "M": 1706,
    "N": 1479,
    "O": 1593,
    "P": 1366,
    "Q": 1593,
    "R": 1479,
    "S": 1366,
    "T": 1251,
    "U": 1479,
    "V": 1366,
    "W": 1933,
    "X": 1366,
    "Y": 1366,
    "Z": 1251,
    "[": 569,
    "\\": 569,
    "]": 569,
    "^": 961,
    "_": 1139,
    "`": 682,
    "a": 1139,
    "b": 1139,
    "c": 1024,
    "d": 1139,
    "e": 1139,
    "f": 569,
    "g": 1139,
    "h": 1139,
    "i": 455,
    "j": 455,
    "k": 1024,
    "l": 455,
    "m": 1706,
    "n": 1139,
    "o": 1139,
    "p": 1139,
    "q": 1139,
    "r": 682,
    "s": 1024,
    "t": 569,
    "u": 1139,
    "v": 1024,
    "w": 1479,
    "x": 1024,
    "y": 1024,
    "z": 1024,
    "{": 684,
    "|": 532,
    "}": 684,
    "~": 1196,
    "\u2019": 455,
    "\u2018": 455,
    "\u201c": 682,
    "\u201d": 682,
    "\u2013": 1139,
    "\u2014": 2048,
    "\u2026": 2048,
    "\u00a3": 1139,
    "\u20ac": 1139,
    "\u00e9": 1139,
    "\u00e8": 1139,
    "\u00fc": 1139,
    "\u00f6": 1139,
    "\u00f1": 1139,
}
_UNKNOWN_UNITS = ARIAL_UNITS["M"]


def title_width_px(text):
    """Rendered width of `text` at 20px Arial, in pixels."""
    return sum(ARIAL_UNITS.get(ch, _UNKNOWN_UNITS) for ch in text or "") * 20.0 / 2048


def title_width_problem(title):
    """None when the title is inside the target width window, else a sentence saying how far off it is."""
    width = title_width_px(title)
    if width > TITLE_PX_TARGET_MAX:
        return f"is {width:.0f} px wide ({len(title)} characters); it must be at most {TITLE_PX_TARGET_MAX} px"
    if width < TITLE_PX_TARGET_MIN:
        return f"is only {width:.0f} px wide ({len(title)} characters); it must be at least {TITLE_PX_TARGET_MIN} px"
    return None


def description_problem(description):
    """None when the description is inside the target length window, else a sentence saying how far off it is."""
    length = len(description or "")
    if length > DESC_CHARS_TARGET_MAX:
        return f"is {length} characters; it must be at most {DESC_CHARS_TARGET_MAX}"
    if length < DESC_CHARS_TARGET_MIN:
        return f"is only {length} characters; it must be at least {DESC_CHARS_TARGET_MIN}"
    return None


def search_field_problems(metadata):
    """{field: sentence} for each AIOSEO field outside its window."""
    problems = {}
    title = title_width_problem(metadata.get("aioseo_title") or "")
    if title:
        problems["aioseo_title"] = title
    description = description_problem(metadata.get("aioseo_description") or "")
    if description:
        problems["aioseo_description"] = description
    return problems


def search_field_distance(metadata):
    """How far the AIOSEO fields sit outside their windows, in a unit-free number (0 = both inside); used to pick
    the best of several failed attempts."""
    title = title_width_px(metadata.get("aioseo_title") or "")
    length = len(metadata.get("aioseo_description") or "")
    return (
        max(0, title - TITLE_PX_TARGET_MAX, TITLE_PX_TARGET_MIN - title) / 10.0
        + max(0, length - DESC_CHARS_TARGET_MAX, DESC_CHARS_TARGET_MIN - length)
    )
