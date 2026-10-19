import json
import os

import pytest

from attributes.app import attributes_lib
from counts.app import counts_lib
from incidents.app import incidents_lib
from officers.app import officers_lib
from scripts import build_data

FIXTURE_DATA = os.path.join(os.path.dirname(__file__), "..", "fixtures", "data")
ROOT = "/nj/use_of_force"


@pytest.fixture(scope="session")
def fixture_build(tmp_path_factory):
    """The fixture data (tests/fixtures/data), built once per session"""
    root = tmp_path_factory.mktemp("build")
    outputs, _ = build_data.build_all(FIXTURE_DATA, str(root))
    return outputs


@pytest.fixture(autouse=True)
def fixture_data(monkeypatch, fixture_build):
    """Points every function at the fixture build, with fresh caches"""
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setenv("API_ROOT", "https://api.example.com")
    for lib, name in [
        (incidents_lib, "incidents"),
        (attributes_lib, "attributes"),
        (officers_lib, "officers"),
    ]:
        monkeypatch.setattr(
            lib, "DEFAULT_DATA_DIR", os.path.dirname(fixture_build[name])
        )
        monkeypatch.setattr(lib, "_db", None)
    monkeypatch.setattr(counts_lib, "DEFAULT_DATA_DIR", fixture_build["counts"])
    monkeypatch.setattr(counts_lib, "_data", None)
    counts_lib.cached_count.cache_clear()


def call(handler, resource, path=None, query=None):
    """Calls handler with a GET event; returns (status code, body)"""
    event = {
        "resource": ROOT + resource,
        "httpMethod": "GET",
        "pathParameters": path,
        "queryStringParameters": query,
    }
    reply = handler(event, None)
    return int(reply["statusCode"]), json.loads(reply["body"])


def form_ids(body):
    return [r["form_id"] for r in body["data"]]
