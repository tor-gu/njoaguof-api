from attributes.app.attributes_api import attributes_handler

from .conftest import call


def get(resource, path=None, query=None):
    return call(attributes_handler, resource, path, query)


def test_codebook():
    status, body = get("/attributes")
    assert status == 200
    assert body["data"] == [
        {
            "attribute": "subject_resistance",
            "table": "incident_subject_resistance",
            "shape": "incident_subject",
            "value_column": "subject_resistance",
        },
        {
            "attribute": "video_type",
            "table": "incident_video_type",
            "shape": "incident",
            "value_column": "video_type",
        },
    ]
    assert "meta" not in body
    assert get("/attributes", query={"page_size": "1"})[0] == 400


def test_incident_shape_rows_keep_source_order():
    status, body = get("/attributes/{attribute}", {"attribute": "video_type"})
    assert status == 200
    # 101's values in source order (Station House before Body Worn), not level order
    assert body["data"] == [
        {"form_id": 101, "video_type": "Station House"},
        {"form_id": 101, "video_type": "Body Worn"},
        {"form_id": 103, "video_type": "Body Worn"},
        {"form_id": 106, "video_type": "Body Worn"},
        {"form_id": 106, "video_type": "Cell Phone"},
    ]
    assert body["meta"] == {"record_count": 5, "page_count": 1}


def test_incident_subject_shape_rows():
    _, body = get("/attributes/{attribute}", {"attribute": "subject_resistance"})
    assert body["data"][2] == {
        "form_id": 101,
        "index": 3,
        "subject_resistance": "Aggressive resistance (attempt to attack or harm)",
    }
    assert [(r["form_id"], r["index"]) for r in body["data"]] == [
        (101, 1),
        (101, 2),
        (101, 3),
        (104, 1),
    ]


def test_attribute_rows_filtered():
    status, body = get(
        "/attributes/{attribute}", {"attribute": "video_type"}, {"year": "2023"}
    )
    assert status == 200
    assert [r["form_id"] for r in body["data"]] == [106, 106]
    assert body["links"]["self"].endswith(
        "/attributes/video_type?year=2023&page_number=1&page_size=100"
    )
    assert (
        get(
            "/attributes/{attribute}",
            {"attribute": "video_type"},
            {"year": "2022", "agency_county": "Morris County"},
        )[0]
        == 404
    )


def test_levels():
    status, body = get("/attributes/{attribute}/levels", {"attribute": "video_type"})
    assert status == 200
    assert body["data"][0] == {
        "attribute": "video_type",
        "position": 1,
        "level": "Body Worn",
    }
    assert [r["position"] for r in body["data"]] == list(range(1, 10))


def test_unknown_attribute():
    assert get("/attributes/{attribute}", {"attribute": "colour"})[0] == 404
    assert get("/attributes/{attribute}/levels", {"attribute": "colour"})[0] == 404
    assert (
        get(
            "/incidents/{form_id}/attributes/{attribute}",
            {"form_id": "101", "attribute": "colour"},
        )[0]
        == 404
    )


def test_incident_attribute_rows():
    status, body = get(
        "/incidents/{form_id}/attributes/{attribute}",
        {"form_id": "106", "attribute": "video_type"},
    )
    assert status == 200
    assert body["data"] == [
        {"form_id": 106, "video_type": "Body Worn"},
        {"form_id": 106, "video_type": "Cell Phone"},
    ]
    # an incident without values, an unknown incident, a bad id
    assert (
        get(
            "/incidents/{form_id}/attributes/{attribute}",
            {"form_id": "102", "attribute": "video_type"},
        )[0]
        == 404
    )
    assert (
        get(
            "/incidents/{form_id}/attributes/{attribute}",
            {"form_id": "999", "attribute": "video_type"},
        )[0]
        == 404
    )
    assert (
        get(
            "/incidents/{form_id}/attributes/{attribute}",
            {"form_id": "x", "attribute": "video_type"},
        )[0]
        == 400
    )
