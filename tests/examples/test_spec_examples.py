"""
Every example reply in the OpenAPI spec, reproduced by the handlers.

Each example's links.self is turned into an API Gateway event and passed to
the handler of the function that serves its path (from the path's
x-amazon-apigateway-integration). The reply must equal the example: data,
links and meta. Runs against the full data (make data), so after a data
refresh the failures show the new values to copy into the spec.
"""

import json
import re
from urllib.parse import parse_qsl, urlsplit

import pytest

from attributes.app import attributes_api
from counts.app import counts_api
from incidents.app import incidents_api
from officers.app import officers_api
from tests.spec_examples import load_examples

API_ROOT = "https://api.tor-gu.com"

HANDLERS = {
    "IncidentsFunction": incidents_api.incidents_handler,
    "AttributesFunction": attributes_api.attributes_handler,
    "OfficersFunction": officers_api.officers_handler,
    "CountsFunction": counts_api.counts_handler,
}


def event_for(resource, url):
    """The API Gateway event for a GET of url, served by resource"""
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == API_ROOT
    pattern = (
        "^" + re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[^/]+)", re.escape(resource)) + "$"
    )
    match = re.match(pattern, parts.path)
    assert match, f"{parts.path} doesn't match {resource}"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    return {
        "resource": resource,
        "path": parts.path,
        "httpMethod": "GET",
        "pathParameters": match.groupdict() or None,
        "queryStringParameters": query or None,
    }


@pytest.mark.parametrize("resource,function,example", load_examples())
def test_spec_example(monkeypatch, resource, function, example):
    monkeypatch.setenv("API_ROOT", API_ROOT)
    reply = HANDLERS[function](event_for(resource, example["links"]["self"]), None)
    body = json.loads(reply["body"])
    assert reply["statusCode"] == 200, body
    expected = {k: example[k] for k in ("data", "links", "meta") if k in example}
    actual = {k: body[k] for k in ("data", "links", "meta") if k in body}
    assert actual == expected, "actual reply:\n" + json.dumps(actual, indent=1)
