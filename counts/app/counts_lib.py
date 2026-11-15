"""
Grouped counts from a torgucols store (counts/data, see scripts/build_data.py):
tables incident, subject (incident_row and the subject dimensions) and
attribute_<x> (incident_row, value), one int32 file per column.

Counting is collections.Counter over zipped columns: no SQLite (it sorts to
GROUP BY, about 13 times slower on Lambda) and no pandas (its import alone
costs more than a count). Codes sort in the API's order, null last.
"""

import os
from functools import lru_cache
from itertools import compress

import torgucols
from uofparams import InvalidRequest, NotFound

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

INCIDENT_DIMENSIONS = [
    "year",
    "month",
    "agency_id",
    "agency",
    "agency_county",
    "incident_municipality",
    "incident_municipality_county",
    "officer_gender",
    "officer_race",
    "video_footage",
]
SUBJECT_DIMENSIONS = ["type", "race", "gender", "arrested", "juvenile", "injured"]
MAX_DIMENSIONS = 3
ATTRIBUTE_PREFIX = "attribute_"

# Text filters -> the incident column they match
FILTER_DIMENSIONS = {
    "agency_id": "agency_id",
    "agency": "agency",
    "agency_county": "agency_county",
    "incident_municipality": "incident_municipality",
    "incident_municipality_county": "incident_municipality_county",
}

# Loaded on first use (only the manifest; columns as they're used) and kept
# while the function is warm
_data = None


def get_data():
    global _data
    if _data is None:
        _data = torgucols.open(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    return _data


def attributes(data):
    """The attributes, from the store's attribute_<x> tables"""
    return {
        name[len(ATTRIBUTE_PREFIX) :]
        for name in data.tables
        if name.startswith(ATTRIBUTE_PREFIX)
    }


def parse_by(data, endpoint, by):
    """
    The by parameter as a tuple of dimensions.

    endpoint is "incidents" (incident dimensions and at most one attribute) or
    "subjects" (incident and subject dimensions).
    """
    if by is None:
        raise InvalidRequest("by is required")
    dimensions = tuple(by.split(","))
    if not 1 <= len(dimensions) <= MAX_DIMENSIONS:
        raise InvalidRequest(f"by needs 1 to {MAX_DIMENSIONS} dimensions")
    if len(set(dimensions)) != len(dimensions):
        raise InvalidRequest(f"Repeated dimension in by={by}")
    known_attributes = attributes(data)
    if endpoint == "incidents":
        allowed = set(INCIDENT_DIMENSIONS) | known_attributes
    else:
        allowed = set(INCIDENT_DIMENSIONS) | set(SUBJECT_DIMENSIONS)
    for d in dimensions:
        if d not in allowed:
            raise InvalidRequest(f"Unknown dimension {d} for /counts/{endpoint}")
    if sum(1 for d in dimensions if d in known_attributes) > 1:
        raise InvalidRequest("by can include at most one attribute")
    return dimensions


def incident_filters(data, filters):
    """The filters as torgucols conditions on the incident table"""
    incident = data.table("incident")
    conditions = []
    date_range = filters.date_range()
    if date_range is not None:
        conditions.append(("between", "date", *date_range))
    for name, dimension in FILTER_DIMENSIONS.items():
        value = getattr(filters, name)
        if value is not None:
            code = incident.code(dimension, value)
            if code is None:
                raise NotFound(f"No incidents with {name} {value}")
            conditions.append(("eq", dimension, code))
    if filters.officer_name_id is not None:
        conditions.append(("eq", "officer_name_id", filters.officer_name_id))
    return tuple(conditions)


def month_decoder(v):
    return f"{v // 100:04d}-{v % 100:02d}"


def count(data, endpoint, dimensions, filters):
    """
    The counts as records {<dimension>: value, ..., "count": n}, ordered by
    the dimensions' codes (declared levels, null last)
    """
    incident = data.table("incident")
    conditions = incident_filters(data, filters)
    # The table joined to incidents through its incident_row column, if any,
    # and {dimension: its column there}
    joined, own = None, {}
    if endpoint == "subjects":
        joined, own = data.table("subject"), {d: d for d in SUBJECT_DIMENSIONS}
    else:
        known_attributes = attributes(data)
        attribute = next((d for d in dimensions if d in known_attributes), None)
        if attribute is not None:
            # One row per (incident, value) pair: an incident counts once per value
            joined = data.table(ATTRIBUTE_PREFIX + attribute)
            own = {attribute: "value"}
    # (table, column) for each dimension
    sources = [(joined, own[d]) if d in own else (incident, d) for d in dimensions]

    if joined is None:
        totals = incident.group(dimensions, conditions)
    else:
        rows = joined.values("incident_row")
        keys = zip(
            *(
                (
                    table.values(column)
                    if table is joined
                    else torgucols.take(table.values(column), rows)
                )
                for table, column in sources
            )
        )
        mask = incident.mask(conditions)
        if mask is not None:
            keys = compress(keys, torgucols.take(mask, rows))
        totals = torgucols.count_keys(keys, [t.null(c) for t, c in sources])

    decoders = [
        month_decoder if (t, c) == (incident, "month") else t.decoder(c)
        for t, c in sources
    ]
    return [
        {**{d: f(v) for d, f, v in zip(dimensions, decoders, key)}, "count": n}
        for key, n in totals
    ]


@lru_cache(maxsize=256)
def cached_count(endpoint, dimensions, filters):
    """count() for the current data, kept while the function is warm"""
    return count(get_data(), endpoint, dimensions, filters)


def get_counts(endpoint, dimensions, filters, page):
    """One page of the counts, and the aux dict for the links"""
    records = cached_count(endpoint, dimensions, filters)
    try:
        return torgucols.page(records, page["page_number"], page["page_size"])
    except (torgucols.EmptyResult, torgucols.PageOutOfRange) as e:
        raise NotFound(str(e)) from None
