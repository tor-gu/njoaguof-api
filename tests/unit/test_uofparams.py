import pytest
from uofparams import (
    Filters,
    InvalidRequest,
    check_allowed,
    incident_filters,
    page_parameters,
)


def test_check_allowed():
    check_allowed({"year": "2021"}, ["year"])
    with pytest.raises(InvalidRequest, match="Unknown query parameter colour"):
        check_allowed({"year": "2021", "colour": "red"}, ["year"])


def test_page_parameters_defaults():
    assert page_parameters({}) == {"page_number": 1, "page_size": 100}
    assert page_parameters({"page_number": "3", "page_size": "7"}) == {
        "page_number": 3,
        "page_size": 7,
    }


@pytest.mark.parametrize(
    "query",
    [
        {"page_number": "0"},
        {"page_number": "x"},
        {"page_size": "0"},
        {"page_size": "-1"},
    ],
)
def test_page_parameters_invalid(query):
    with pytest.raises(InvalidRequest):
        page_parameters(query)


def test_incident_filters():
    filters, link_params = incident_filters(
        {
            "year": "2021",
            "agency_county": "Essex County",
            "officer_name_id": "501",
            "page_size": "5",
        }
    )
    assert filters == Filters(
        year=2021, agency_county="Essex County", officer_name_id=501
    )
    assert link_params == {
        "year": "2021",
        "agency_county": "Essex County",
        "officer_name_id": "501",
    }


@pytest.mark.parametrize(
    "query",
    [
        {"year": "twenty"},
        {"year": "2021.0"},
        {"officer_name_id": "-5"},
        {"start_date": "2021/01/01"},
        {"start_date": "20210101"},
        {"end_date": "2021-02-30"},
        {"start_date": "2022-01-01", "end_date": "2021-12-31"},
        {"agency_county": "Essex"},
        {"incident_municipality_county": "Nowhere County"},
        {"agency": ""},
    ],
)
def test_incident_filters_invalid(query):
    with pytest.raises(InvalidRequest):
        incident_filters(query)


def test_date_range():
    assert Filters().date_range() is None
    assert Filters(year=2021).date_range() == (20210101, 20211231)
    assert Filters(start_date="2021-06-01").date_range() == (20210601, 99991231)
    assert Filters(year=2021, end_date="2021-03-31").date_range() == (
        20210101,
        20210331,
    )
    # year and dates combine as AND
    assert Filters(year=2021, start_date="2020-06-01").date_range() == (
        20210101,
        20211231,
    )
