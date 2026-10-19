"""Request parameters: errors, paging and the incident filters"""

import re
from dataclasses import dataclass, fields
from datetime import date

from torguapi import TorguapiInvalidRequest, torguapi_get_page_parameters


class InvalidRequest(Exception):
    """A bad request (400)"""

    pass


class NotFound(Exception):
    """Nothing matches the request (404)"""

    pass


COUNTIES = [
    "Atlantic County",
    "Bergen County",
    "Burlington County",
    "Camden County",
    "Cape May County",
    "Cumberland County",
    "Essex County",
    "Gloucester County",
    "Hudson County",
    "Hunterdon County",
    "Mercer County",
    "Middlesex County",
    "Monmouth County",
    "Morris County",
    "Ocean County",
    "Passaic County",
    "Salem County",
    "Somerset County",
    "Sussex County",
    "Union County",
    "Warren County",
]

PAGE_PARAMS = ["page_number", "page_size"]

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Filters:
    """The incident filters of a request (None = not given); hashable"""

    year: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    agency: str | None = None
    agency_county: str | None = None
    incident_municipality: str | None = None
    incident_municipality_county: str | None = None
    officer_name_id: int | None = None

    def date_range(self):
        """
        The (first, last) incident_date_1 selected by year, start_date and
        end_date, as yyyymmdd ints, or None when none of them is given
        """
        first, last = [], []
        if self.year is not None:
            first.append(self.year * 10000 + 101)
            last.append(self.year * 10000 + 1231)
        if self.start_date is not None:
            first.append(int(self.start_date.replace("-", "")))
        if self.end_date is not None:
            last.append(int(self.end_date.replace("-", "")))
        if not first and not last:
            return None
        return (max(first) if first else 0, min(last) if last else 99991231)


FILTER_PARAMS = [f.name for f in fields(Filters)]


def query_parameters(event):
    """The event's query parameters as a dict (never None)"""
    return event.get("queryStringParameters") or {}


def path_parameters(event):
    """The event's path parameters as a dict (never None)"""
    return event.get("pathParameters") or {}


def check_allowed(query, allowed):
    """InvalidRequest for any query parameter not in allowed"""
    unknown = sorted(set(query) - set(allowed))
    if unknown:
        raise InvalidRequest(f"Unknown query parameter {unknown[0]}")


def page_parameters(query):
    """page_number (default 1) and page_size (default 100) as ints"""
    try:
        params = torguapi_get_page_parameters(query)
    except TorguapiInvalidRequest as e:
        raise InvalidRequest(str(e))
    params.setdefault("page_number", 1)
    if params["page_number"] < 1:
        raise InvalidRequest(f"Invalid page_number {query.get('page_number')}")
    return params


def parse_int(name, value):
    if not value.isdigit() or not value.isascii():
        raise InvalidRequest(f"Invalid {name} {value}")
    return int(value)


def parse_date(name, value):
    if not DATE_PATTERN.match(value):
        raise InvalidRequest(f"Invalid {name} {value} (expected YYYY-MM-DD)")
    try:
        date(*(int(p) for p in value.split("-")))
    except ValueError:
        raise InvalidRequest(f"Invalid {name} {value}")
    return value


def parse_county(name, value):
    if value not in COUNTIES:
        raise InvalidRequest(f"Invalid {name} {value}")
    return value


def parse_text(name, value):
    if value == "":
        raise InvalidRequest(f"Empty {name}")
    return value


PARSERS = {
    "year": parse_int,
    "start_date": parse_date,
    "end_date": parse_date,
    "agency": parse_text,
    "agency_county": parse_county,
    "incident_municipality": parse_text,
    "incident_municipality_county": parse_county,
    "officer_name_id": parse_int,
}


def incident_filters(query):
    """
    Checks and converts the incident filters in the query parameters.

    Returns:
        Filters
        dict of the given filters as strings, for the links (only parameters
        that were checked, as torguapi_make_links_and_meta asks)
    """
    values = {}
    link_params = {}
    for name in FILTER_PARAMS:
        if name in query:
            values[name] = PARSERS[name](name, query[name])
            link_params[name] = query[name]
    filters = Filters(**values)
    if (
        filters.start_date
        and filters.end_date
        and filters.end_date < filters.start_date
    ):
        raise InvalidRequest("end_date is before start_date")
    return filters, link_params
