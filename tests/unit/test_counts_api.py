from collections import Counter

import pytest
from uofparams import Filters

from counts.app.counts_api import counts_handler
from incidents.app import incidents_lib

from .conftest import call


def get(endpoint, query):
    return call(counts_handler, f"/counts/{endpoint}", None, query)


def counts(endpoint, query):
    status, body = get(endpoint, query)
    assert status == 200, body
    return [tuple(r.values()) for r in body["data"]]


def test_by_year():
    assert counts("incidents", {"by": "year"}) == [(2021, 2), (2022, 2), (2023, 2)]


def test_by_month():
    assert counts("incidents", {"by": "month", "year": "2021"}) == [
        ("2021-03", 1),
        ("2021-07", 1),
    ]


def test_levels_order_and_null_last():
    assert counts("incidents", {"by": "agency_county"}) == [
        ("Essex County", 3),
        ("Gloucester County", 1),
        ("Morris County", 1),
        (None, 1),
    ]
    # video_footage levels: Yes, No, Unknown
    assert counts("incidents", {"by": "video_footage"}) == [
        ("Yes", 3),
        ("No", 2),
        ("Unknown", 1),
    ]


def test_attribute_counts_each_value_once():
    assert counts("incidents", {"by": "video_type"}) == [
        ("Body Worn", 3),
        ("Cell Phone", 1),
        ("Station House", 1),
    ]
    assert counts("incidents", {"by": "year,video_type", "year": "2023"}) == [
        (2023, "Body Worn", 1),
        (2023, "Cell Phone", 1),
    ]
    assert counts("incidents", {"by": "subject_resistance"}) == [
        ("Aggressive resistance (attempt to attack or harm)", 1),
        ("Attempt to flee", 1),
        ("Verbal", 1),
    ]


def test_subject_counts():
    assert counts("subjects", {"by": "race"}) == [
        ("Black", 3),
        ("Hispanic", 1),
        ("White", 2),
        (None, 2),
    ]
    assert counts("subjects", {"by": "arrested"}) == [(False, 3), (True, 4), (None, 1)]
    assert counts(
        "subjects", {"by": "agency_county,gender", "officer_name_id": "501"}
    ) == [
        ("Essex County", "Male", 1),
        ("Essex County", "Female", 1),
    ]


def test_links_carry_by_and_filters():
    status, body = get(
        "subjects",
        {"by": "agency_county,race", "agency_county": "Essex County", "page_size": "2"},
    )
    assert status == 200
    assert body["meta"] == {"record_count": 2, "page_count": 1}
    assert body["links"]["self"] == (
        "https://api.example.com/nj/use_of_force/counts/subjects"
        "?agency_county=Essex%20County&by=agency_county%2Crace&page_number=1&page_size=2"
    )


@pytest.mark.parametrize(
    "endpoint,query",
    [
        ("incidents", {}),
        ("incidents", {"by": ""}),
        ("incidents", {"by": "year,month,agency,agency_county"}),
        ("incidents", {"by": "year,year"}),
        ("incidents", {"by": "colour"}),
        ("incidents", {"by": "race"}),
        ("incidents", {"by": "video_type,subject_resistance"}),
        ("subjects", {"by": "video_type"}),
        ("incidents", {"by": "year", "colour": "red"}),
        ("incidents", {"by": "year", "year": "x"}),
    ],
)
def test_bad_requests(endpoint, query):
    assert get(endpoint, query)[0] == 400


def test_not_found():
    assert get("incidents", {"by": "year", "agency": "Nowhere PD"})[0] == 404
    assert get("incidents", {"by": "year", "year": "2019"})[0] == 404
    assert get("incidents", {"by": "year", "page_number": "2"})[0] == 404


@pytest.mark.parametrize(
    "dimensions,filters",
    [
        (("agency", "officer_gender"), Filters()),
        (("incident_municipality", "officer_race"), Filters(agency="Newark PD")),
        (
            ("incident_municipality_county", "video_footage"),
            Filters(start_date="2021-06-01"),
        ),
    ],
)
def test_counts_match_incident_rows(dimensions, filters):
    """Counts agree with counting the decoded rows of /incidents"""
    db = incidents_lib.get_db()
    rows, _ = incidents_lib.get_incidents(
        db, filters, {"page_number": 1, "page_size": 100}
    )
    source = {"agency": "agency_name"}
    expected = Counter(tuple(r[source.get(d, d)] for d in dimensions) for r in rows)
    query = {"by": ",".join(dimensions)}
    query.update({k: str(v) for k, v in vars(filters).items() if v is not None})
    actual = {tuple(r[:-1]): r[-1] for r in counts("incidents", query)}
    assert actual == dict(expected)
