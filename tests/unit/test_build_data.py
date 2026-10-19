import array
import json
import os
import shutil
import sqlite3

import pytest

from scripts import build_data

from .conftest import FIXTURE_DATA


def read_i32(directory, name):
    a = array.array("i")
    with open(os.path.join(directory, f"{name}.i32"), "rb") as f:
        a.frombytes(f.read())
    return a.tolist()


def test_row_counts(fixture_build):
    con = sqlite3.connect(fixture_build["incidents"])
    assert con.execute("SELECT COUNT(*) FROM incident").fetchone()[0] == 6
    assert con.execute("SELECT COUNT(*) FROM subject").fetchone()[0] == 8
    con = sqlite3.connect(fixture_build["attributes"])
    assert con.execute("SELECT COUNT(*) FROM incident_video_type").fetchone()[0] == 5
    assert (
        con.execute("SELECT COUNT(*) FROM incident_subject_resistance").fetchone()[0]
        == 4
    )
    con = sqlite3.connect(fixture_build["officers"])
    assert con.execute("SELECT COUNT(*) FROM officer_name_variants").fetchone()[0] == 4


def test_storage(fixture_build):
    con = sqlite3.connect(fixture_build["incidents"])
    storage = dict(
        con.execute(
            'SELECT "column", storage FROM columns WHERE "table" = \'incident\''
        )
    )
    assert storage["form_id"] == "integer"
    assert storage["incident_date_1"] == "date"
    assert storage["agency_county"] == "code"
    assert storage["agency_name"] == "code"
    assert storage["officer_injured"] == "logical"
    assert storage["report_number"] == "text"
    row = con.execute(
        "SELECT incident_date_1, officer_injured, incident_case_number FROM incident WHERE form_id = 104"
    ).fetchone()
    assert row == (20220630, None, None)


def test_codes_follow_levels(fixture_build):
    """Factor codes are level positions; character codes are sorted positions"""
    con = sqlite3.connect(fixture_build["incidents"])
    labels = {
        (t, c, code): label for t, c, code, label in con.execute("SELECT * FROM labels")
    }
    assert labels[("incident", "agency_county", 1)] == "Atlantic County"
    assert labels[("incident", "video_footage", 3)] == "Unknown"
    assert labels[("incident", "agency_name", 1)] == "Atlantic City PD"


def test_agency_order(fixture_build):
    con = sqlite3.connect(fixture_build["incidents"])
    rows = con.execute(
        "SELECT agency_name, agency_county, incident_count FROM agency ORDER BY rowid"
    )
    assert rows.fetchall() == [
        ("Atlantic City PD", None, 1),
        ("Newark PD", "Essex County", 3),
        ("Washington Twp PD", "Gloucester County", 1),
        ("Washington Twp PD", "Morris County", 1),
    ]


def test_counts_columns(fixture_build):
    d = fixture_build["counts"]
    assert read_i32(d, "inc.form_id") == [101, 102, 103, 104, 105, 106]
    assert read_i32(d, "inc.month") == [202103, 202107, 202201, 202206, 202302, 202312]
    assert read_i32(d, "inc.officer_name_id") == [500, 501, 500, 502, 0, 501]
    assert read_i32(d, "subj.inc_row") == [0, 0, 1, 2, 3, 3, 4, 5]
    # 0 null, 1 false, 2 true
    assert read_i32(d, "subj.arrested") == [2, 0, 1, 2, 2, 1, 1, 2]
    # Distinct (incident row, code) pairs, sorted
    assert read_i32(d, "a_video_type.row") == [0, 0, 2, 5, 5]
    assert read_i32(d, "a_video_type.v") == [1, 7, 1, 1, 3]
    with open(os.path.join(d, "labels.json")) as f:
        labels = json.load(f)["labels"]
    assert labels["incident.agency"] == [
        "Atlantic City PD",
        "Newark PD",
        "Washington Twp PD",
    ]
    assert labels["attribute.video_type"][0] == "Body Worn"


@pytest.fixture
def fixture_copy(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURE_DATA, data)
    return data


def append_line(path, line):
    with open(path, "a") as f:
        f.write(line + "\n")


def test_repeated_attribute_value_fails(fixture_copy, tmp_path):
    append_line(fixture_copy / "incident_video_type.csv", '103,"Body Worn"')
    with pytest.raises(build_data.BuildError, match="repeated"):
        build_data.build_all(str(fixture_copy), str(tmp_path / "out"))


def test_value_not_in_levels_fails(fixture_copy, tmp_path):
    append_line(fixture_copy / "incident_video_type.csv", '102,"Drone"')
    with pytest.raises(build_data.BuildError, match="not in levels"):
        build_data.build_all(str(fixture_copy), str(tmp_path / "out"))


def test_header_mismatch_fails(fixture_copy, tmp_path):
    path = fixture_copy / "officer_name_variants.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(['"officer_name_id","name"'] + lines[1:]) + "\n")
    with pytest.raises(build_data.BuildError, match="header"):
        build_data.build_all(str(fixture_copy), str(tmp_path / "out"))


def test_reads_gzipped_csv(fixture_copy, tmp_path):
    import gzip

    path = fixture_copy / "subject.csv"
    with open(path, "rb") as f, gzip.open(str(path) + ".gz", "wb") as g:
        g.write(f.read())
    os.remove(path)
    outputs, _ = build_data.build_all(str(fixture_copy), str(tmp_path / "out"))
    con = sqlite3.connect(outputs["incidents"])
    assert con.execute("SELECT COUNT(*) FROM subject").fetchone()[0] == 8
