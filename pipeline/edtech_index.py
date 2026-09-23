"""
Fetches a show's Edtech-Index-style constituent table from its Google Sheet
and normalizes it into the shape /shows/{id}/index-snapshot expects.

Deliberately reads the sheet's public CSV export
(https://docs.google.com/spreadsheets/d/{id}/export?format=csv&gid={gid}),
not the Sheets API - confirmed live (2026-09-21) that the real sheet is
shared "anyone with the link can view", so the CSV export needs no
credentials at all. This is a real dependency, not a nice-to-have: if
sharing on that sheet is ever tightened, this starts failing, which is why
process_index_refresh() (tick.py) is written to keep serving the last good
snapshot rather than blank the page, and to log/notify loudly rather than
fail silently.

All market-data math (live price, day change, YTD change, position value)
stays in the sheet itself (GOOGLEFINANCE formulas the user maintains) - this
module only parses what the sheet already computed. It never assumes a
fixed row count or a fixed set of tickers: the constituent list is read
fresh and returned whole on every call, so tickers can be added or removed
in the sheet at any time with no code change needed here.
"""

import csv
import io
import logging
import re
from datetime import datetime, timezone

import requests

from retry import call_with_retries

logger = logging.getLogger("net_gain.edtech_index")

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)

# 0-based index of the sheet's header row ("Ticker", "Company Name", ...) -
# row 5 in the sheet UI. Rows above this are the title/summary block; rows
# below are constituents.
HEADER_ROW_INDEX = 4

# Column order as of 2026-09-21 (the two YTD columns were added at the
# user's request, appended after the original 8). A short row (sheet
# temporarily missing the YTD columns) is padded, not treated as an error -
# see fetch_index_snapshot()'s row-length tolerance below.
COLUMN_COUNT = 10


class EdtechIndexError(RuntimeError):
    pass


def _csv_export_url(sheet_id, gid):
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _parse_sheet_url(sheet_url):
    """
    Accepts either the full editor URL (.../spreadsheets/d/{id}/edit?gid=0#gid=0,
    what a human copies from the browser address bar) or a bare sheet id, so
    ng_index_sheet_url can be set to whatever was easiest to paste.
    """
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_url)
    sheet_id = match.group(1) if match else sheet_url.strip()

    gid_match = re.search(r"[?#&]gid=(\d+)", sheet_url)
    gid = gid_match.group(1) if gid_match else "0"

    return sheet_id, gid


def _parse_money(raw):
    if not raw or not raw.strip():
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", raw)
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_percent(raw):
    if not raw or not raw.strip():
        return None
    cleaned = raw.replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_index_snapshot(sheet_url, timeout=30):
    """
    Returns a dict ready to POST to /net-gain/v1/shows/{id}/index-snapshot.
    Raises EdtechIndexError on any failure (network, unparseable sheet, zero
    constituent rows) - callers must catch this and keep the previous
    snapshot in place rather than overwrite it with a partial result; a
    down/misconfigured sheet should never blank a previously-working page.
    """
    sheet_id, gid = _parse_sheet_url(sheet_url)
    url = _csv_export_url(sheet_id, gid)

    def do_request():
        response = requests.get(url, timeout=timeout)
        if response.status_code >= 500 or response.status_code == 429:
            raise requests.exceptions.ConnectionError(
                f"GET {url} returned {response.status_code}"
            )
        return response

    try:
        response = call_with_retries(do_request, RETRYABLE_EXCEPTIONS)
    except Exception as exc:
        raise EdtechIndexError(f"Could not fetch sheet CSV: {exc}") from exc

    if not response.ok:
        raise EdtechIndexError(
            f"GET {url} failed ({response.status_code}) - is the sheet still "
            "shared as 'anyone with the link can view'?"
        )

    rows = list(csv.reader(io.StringIO(response.text)))
    if len(rows) <= HEADER_ROW_INDEX:
        raise EdtechIndexError(
            f"Sheet returned only {len(rows)} row(s) - expected a header row at "
            f"row {HEADER_ROW_INDEX + 1}. Has the sheet's layout changed?"
        )

    def cell(row_index, col_index):
        row = rows[row_index] if row_index < len(rows) else []
        return row[col_index].strip() if col_index < len(row) else ""

    # Row 2 (index 1): Baseline Allocation / Daily Index Change ($).
    # Row 3 (index 2): Total Index Value / Daily Index Change (%).
    total_index_value = _parse_money(cell(2, 1))
    daily_change_dollar = _parse_money(cell(1, 4))
    daily_change_percent = _parse_percent(cell(2, 4))

    constituents = []
    ytd_values = []
    for row in rows[HEADER_ROW_INDEX + 1:]:
        if not row or not row[0].strip():
            continue  # blank trailing rows - the sheet's used range often overshoots real data.

        padded = list(row) + [""] * (COLUMN_COUNT - len(row))
        (
            ticker, exchange, company, country, segment,
            price, day_change, position_value, _ytd_start, ytd_change,
        ) = padded[:COLUMN_COUNT]

        ticker = ticker.strip()
        if not ticker:
            continue

        ytd_change_val = _parse_percent(ytd_change)
        if ytd_change_val is not None:
            ytd_values.append(ytd_change_val)

        constituents.append({
            "ticker": ticker,
            "exchange": exchange.strip(),
            "company": company.strip(),
            "country": country.strip(),
            "segment": segment.strip(),
            "price": _parse_money(price),
            "day_change_percent": _parse_percent(day_change),
            "position_value": _parse_money(position_value),
            "ytd_change_percent": ytd_change_val,
        })

    if not constituents:
        raise EdtechIndexError(
            "Parsed zero constituent rows from the sheet - refusing to publish "
            "an empty index rather than wipe out a real one."
        )

    # Equal-weighted portfolio YTD, computed here rather than read from a
    # fixed header cell (the sheet has no reliable single cell for this) -
    # the mathematically correct aggregate for a sheet where every position
    # starts at the same $1,000 allocation, and it self-adjusts as
    # constituents are added/removed since it's just an average of whatever
    # rows are actually present this run.
    ytd_change_percent = round(sum(ytd_values) / len(ytd_values), 4) if ytd_values else None

    logger.info(
        "Fetched %d constituent(s) from index sheet %s (gid=%s).",
        len(constituents), sheet_id, gid,
    )

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "total_index_value": total_index_value,
        "daily_change_dollar": daily_change_dollar,
        "daily_change_percent": daily_change_percent,
        "ytd_change_percent": ytd_change_percent,
        "constituent_count": len(constituents),
        "constituents": constituents,
    }
