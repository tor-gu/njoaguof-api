"""
Grouped counts from int32 columns (counts/data, see scripts/build_data.py).

Counting is collections.Counter over zipped columns: no SQLite (it sorts to
GROUP BY, about 13 times slower on Lambda) and no pandas (its import alone
costs more than a count). 0 means null, and codes sort in the API's order.
"""

import array
import json
import os
import sys
from collections import Counter
from functools import lru_cache
from itertools import compress

from uofparams import InvalidRequest, NotFound

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

INCIDENT_DIMENSIONS = [
    "year",
    "month",
    "agency",
    "agency_county",
    "incident_municipality",
    "incident_municipality_county",
    "officer_gender",
    "officer_race",
    "video_footage",
]
SUBJECT_DIMENSIONS = ["type", "race", "gender", "arrested", "juvenile", "injured"]
LOGICAL_DIMENSIONS = {"arrested", "juvenile", "injured"}
MAX_DIMENSIONS = 3

# Text filters -> the incident column they match
FILTER_DIMENSIONS = {
    "agency": "agency",
    "agency_county": "agency_county",
    "incident_municipality": "incident_municipality",
    "incident_municipality_county": "incident_municipality_county",
}


class CountData:
    """The columns, loaded on first use and kept while the function is warm"""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        with open(os.path.join(data_dir, "labels.json"), encoding="utf-8") as f:
            meta = json.load(f)
        if meta["byteorder"] != sys.byteorder:
            raise RuntimeError(f"counts data is {meta['byteorder']}-endian")
        self.labels = meta["labels"]
        self.attributes = sorted(
            k[len("attribute.") :] for k in self.labels if k.startswith("attribute.")
        )
        self._columns = {}

    def column(self, name):
        """A column as a list (indexing a list is faster than an array)"""
        if name not in self._columns:
            values = array.array("i")
            with open(os.path.join(self.data_dir, f"{name}.i32"), "rb") as f:
                values.frombytes(f.read())
            self._columns[name] = values.tolist()
        return self._columns[name]

    def incident_column(self, dimension):
        return self.column(f"inc.{dimension}")

    def code(self, dimension, label):
        """The code of an incident dimension's label, or None"""
        labels = self.labels[f"incident.{dimension}"]
        try:
            return labels.index(label) + 1
        except ValueError:
            return None


_data = None


def get_data():
    global _data
    if _data is None:
        _data = CountData(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    return _data


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
    if endpoint == "incidents":
        allowed = set(INCIDENT_DIMENSIONS) | set(data.attributes)
    else:
        allowed = set(INCIDENT_DIMENSIONS) | set(SUBJECT_DIMENSIONS)
    for d in dimensions:
        if d not in allowed:
            raise InvalidRequest(f"Unknown dimension {d} for /counts/{endpoint}")
    if sum(1 for d in dimensions if d in data.attributes) > 1:
        raise InvalidRequest("by can include at most one attribute")
    return dimensions


def incident_mask(data, filters):
    """
    A bytearray marking the incidents that match the filters, or None when
    there are no filters
    """
    conditions = []
    date_range = filters.date_range()
    if date_range is not None:
        first, last = date_range
        conditions.append((data.incident_column("date"), lambda v: first <= v <= last))
    for name, dimension in FILTER_DIMENSIONS.items():
        value = getattr(filters, name)
        if value is not None:
            code = data.code(dimension, value)
            if code is None:
                raise NotFound(f"No incidents with {name} {value}")
            conditions.append((data.incident_column(dimension), code.__eq__))
    if filters.officer_name_id is not None:
        conditions.append(
            (data.incident_column("officer_name_id"), filters.officer_name_id.__eq__)
        )
    if not conditions:
        return None
    rows = range(len(data.incident_column("form_id")))
    for values, test in conditions:
        rows = [i for i in rows if test(values[i])]
    mask = bytearray(len(data.incident_column("form_id")))
    for i in rows:
        mask[i] = 1
    return mask


def decoder(data, dimension):
    """Function from a dimension's code to its API value"""
    if dimension == "year":
        return lambda v: v
    if dimension == "month":
        return lambda v: f"{v // 100:04d}-{v % 100:02d}"
    if dimension in LOGICAL_DIMENSIONS:
        return (None, False, True).__getitem__
    if dimension in data.attributes:
        key = f"attribute.{dimension}"
    elif dimension in SUBJECT_DIMENSIONS:
        key = f"subject.{dimension}"
    else:
        key = f"incident.{dimension}"
    labels = [None] + data.labels[key]
    return labels.__getitem__


def count(data, endpoint, dimensions, filters):
    """
    The counts as records {<dimension>: value, ..., "count": n}, ordered by
    the dimensions' codes (declared levels, null last)
    """
    mask = incident_mask(data, filters)
    if endpoint == "incidents":
        attributes = [d for d in dimensions if d in data.attributes]
        if not attributes:
            keys = zip(*(data.incident_column(d) for d in dimensions))
            if mask is not None:
                keys = compress(keys, mask)
        else:
            # One (incident, value) pair per row: an incident counts once per value
            rows = data.column(f"a_{attributes[0]}.row")
            values = data.column(f"a_{attributes[0]}.v")
            keys = zip(
                *(
                    (
                        values
                        if d in data.attributes
                        else map(data.incident_column(d).__getitem__, rows)
                    )
                    for d in dimensions
                )
            )
            if mask is not None:
                keys = compress(keys, map(mask.__getitem__, rows))
    else:
        inc_row = data.column("subj.inc_row")
        keys = zip(
            *(
                (
                    data.column(f"subj.{d}")
                    if d in SUBJECT_DIMENSIONS
                    else map(data.incident_column(d).__getitem__, inc_row)
                )
                for d in dimensions
            )
        )
        if mask is not None:
            keys = compress(keys, map(mask.__getitem__, inc_row))

    counts = sorted(Counter(keys).items(), key=lambda kv: [(v == 0, v) for v in kv[0]])
    decoders = [decoder(data, d) for d in dimensions]
    return [
        {**{d: f(v) for d, f, v in zip(dimensions, decoders, key)}, "count": n}
        for key, n in counts
    ]


@lru_cache(maxsize=256)
def cached_count(endpoint, dimensions, filters):
    """count() for the current data, kept while the function is warm"""
    return count(get_data(), endpoint, dimensions, filters)


def get_counts(endpoint, dimensions, filters, page):
    """One page of the counts, and the aux dict for the links"""
    records = cached_count(endpoint, dimensions, filters)
    if not records:
        raise NotFound("No matching records")
    page_number, page_size = page["page_number"], page["page_size"]
    page_count = (len(records) - 1) // page_size + 1
    if page_number > page_count:
        raise NotFound(f"Page number {page_number} not found")
    start = (page_number - 1) * page_size
    aux = {
        "page_number": page_number,
        "page_size": page_size,
        "record_count": len(records),
    }
    return records[start : start + page_size], aux
