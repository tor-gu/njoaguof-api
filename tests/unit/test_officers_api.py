from officers.app.officers_api import officers_handler

from .conftest import call


def get(resource, officer_name_id, query=None):
    return call(officers_handler, resource, {"officer_name_id": officer_name_id}, query)


def test_officer():
    status, body = get("/officers/{officer_name_id}", "500")
    assert status == 200
    assert body["data"] == [
        {"officer_name_id": 500, "officer_name": "Ann Smith", "incident_count": 2}
    ]
    assert body["links"] == {
        "self": "https://api.example.com/nj/use_of_force/officers/500"
    }
    assert "meta" not in body


def test_name_variants_in_source_order():
    status, body = get("/officers/{officer_name_id}/name_variants", "500")
    assert status == 200
    assert body["data"] == [
        {"officer_name_id": 500, "officer_name": "Ann Smith"},
        {"officer_name_id": 500, "officer_name": "Ann R. Smith"},
    ]


def test_officer_errors():
    assert get("/officers/{officer_name_id}", "999")[0] == 404
    assert get("/officers/{officer_name_id}/name_variants", "999")[0] == 404
    assert get("/officers/{officer_name_id}", "abc")[0] == 400
    assert get("/officers/{officer_name_id}", "500", {"page_size": "2"})[0] == 400
