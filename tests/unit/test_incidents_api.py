import pytest

from incidents.app.incidents_api import incidents_handler

from .conftest import call, form_ids


def get(resource, path=None, query=None):
    return call(incidents_handler, resource, path, query)


def test_incidents_all():
    status, body = get("/incidents")
    assert status == 200
    assert form_ids(body) == [101, 102, 103, 104, 105, 106]
    assert body["meta"] == {"record_count": 6, "page_count": 1}
    assert body["links"] == {
        "self": "https://api.example.com/nj/use_of_force/incidents?page_number=1&page_size=100"
    }


@pytest.mark.parametrize(
    "query,expected",
    [
        ({"year": "2021"}, [101, 102]),
        ({"start_date": "2021-07-10", "end_date": "2022-01-15"}, [102, 103]),
        ({"agency": "Washington Twp PD"}, [103, 104]),
        ({"agency": "Washington Twp PD", "agency_county": "Morris County"}, [104]),
        ({"agency_county": "Essex County"}, [101, 102, 106]),
        ({"incident_municipality": "Newark city"}, [101, 102]),
        ({"incident_municipality_county": "Atlantic County"}, [105]),
        ({"officer_name_id": "500"}, [101, 103]),
        ({"year": "2023", "officer_name_id": "501"}, [106]),
    ],
)
def test_incidents_filtered(query, expected):
    status, body = get("/incidents", query=query)
    assert status == 200
    assert form_ids(body) == expected


@pytest.mark.parametrize(
    "query",
    [
        {"agency": "Nowhere PD"},
        {"year": "2019"},
        {"agency_county": "Salem County"},
        {"page_number": "2"},
    ],
)
def test_incidents_not_found(query):
    status, body = get("/incidents", query=query)
    assert status == 404
    assert body["errors"][0]["status"] == "404"


@pytest.mark.parametrize(
    "query", [{"colour": "red"}, {"year": "x"}, {"agency_county": "Essex"}]
)
def test_incidents_bad_request(query):
    status, _ = get("/incidents", query=query)
    assert status == 400


def test_incidents_paging_links():
    status, body = get(
        "/incidents",
        query={"agency_county": "Essex County", "page_size": "1", "page_number": "2"},
    )
    assert status == 200
    assert form_ids(body) == [102]
    assert body["meta"] == {"record_count": 3, "page_count": 3}
    base = (
        "https://api.example.com/nj/use_of_force/incidents?agency_county=Essex%20County"
    )
    assert body["links"] == {
        "self": f"{base}&page_number=2&page_size=1",
        "previous": f"{base}&page_number=1&page_size=1",
        "next": f"{base}&page_number=3&page_size=1",
    }


def test_incident_values():
    status, body = get("/incidents/{form_id}", {"form_id": "105"})
    assert status == 200
    assert "meta" not in body
    assert body["links"] == {
        "self": "https://api.example.com/nj/use_of_force/incidents/105"
    }
    assert body["data"] == [
        {
            "form_id": 105,
            "report_number": "UOF23-2-5",
            "incident_case_number": "23-0005",
            "incident_date_1": "2023-02-01",
            "agency_county": None,
            "agency_name": "Atlantic City PD",
            "incident_municipality": "Atlantic City city",
            "incident_municipality_county": "Atlantic County",
            "officer_name_id": None,
            "officer_name": None,
            "officer_age": 29,
            "officer_race": None,
            "officer_rank": None,
            "officer_gender": None,
            "officer_injured": False,
            "video_footage": "No",
            "indoors": False,
            "outdoors": True,
            "subject_count": 1,
            "subject_injured_count": 0,
            "other_officer_involved": None,
            "officer_in_uniform": True,
        }
    ]


def test_incident_nulls():
    _, body = get("/incidents/{form_id}", {"form_id": "104"})
    record = body["data"][0]
    assert record["incident_case_number"] is None
    assert record["officer_injured"] is None
    assert record["officer_in_uniform"] is False


def test_incident_not_found_and_bad_id():
    assert get("/incidents/{form_id}", {"form_id": "999"})[0] == 404
    assert get("/incidents/{form_id}", {"form_id": "abc"})[0] == 400
    assert get("/incidents/{form_id}", {"form_id": "101"}, {"page_size": "5"})[0] == 400


def test_incident_subjects():
    status, body = get("/incidents/{form_id}/subjects", {"form_id": "101"})
    assert status == 200
    assert [(r["form_id"], r["index"]) for r in body["data"]] == [(101, 1), (101, 2)]
    assert body["data"][1] == {
        "form_id": 101,
        "index": 2,
        "arrested": None,
        "type": "Person",
        "age": 16,
        "juvenile": True,
        "race": "White",
        "gender": "Female",
        "injured": True,
        "injured_prior": None,
    }
    assert body["links"]["self"].endswith(
        "/incidents/101/subjects?page_number=1&page_size=100"
    )
    assert get("/incidents/{form_id}/subjects", {"form_id": "999"})[0] == 404


def test_subjects_filtered():
    status, body = get("/subjects", query={"agency_county": "Essex County"})
    assert status == 200
    assert [(r["form_id"], r["index"]) for r in body["data"]] == [
        (101, 1),
        (101, 2),
        (102, 1),
        (106, 1),
    ]
    _, body = get("/subjects")
    assert body["meta"]["record_count"] == 8


def test_agencies():
    status, body = get("/agencies", query={"page_size": "3"})
    assert status == 200
    assert body["data"] == [
        {"agency_name": "Atlantic City PD", "agency_county": None, "incident_count": 1},
        {
            "agency_name": "Newark PD",
            "agency_county": "Essex County",
            "incident_count": 3,
        },
        {
            "agency_name": "Washington Twp PD",
            "agency_county": "Gloucester County",
            "incident_count": 1,
        },
    ]
    assert body["meta"] == {"record_count": 4, "page_count": 2}
    assert get("/agencies", query={"year": "2021"})[0] == 400


def test_unknown_resource():
    status, _ = get("/nowhere")
    assert status == 404
