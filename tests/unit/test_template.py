"""template.yaml and the spec agree on which function serves which path"""

import os
import re

import yaml

REPO = os.path.join(os.path.dirname(__file__), "..", "..")


class CfnLoader(yaml.SafeLoader):
    """Reads CloudFormation's short-form tags (!Ref, !Sub, ...) as plain values"""


CfnLoader.add_multi_constructor(
    "!",
    lambda loader, suffix, node: (
        loader.construct_scalar(node)
        if isinstance(node, yaml.ScalarNode)
        else loader.construct_sequence(node)
    ),
)


def load(name, loader=yaml.SafeLoader):
    with open(os.path.join(REPO, name), encoding="utf-8") as f:
        return yaml.load(f, Loader=loader)


def test_template_events_match_spec_integrations():
    template = load("template.yaml", CfnLoader)
    spec = load("use-of-force-openapi.yaml")
    events = {
        (event["Properties"]["Path"], name)
        for name, resource in template["Resources"].items()
        if resource["Type"] == "AWS::Serverless::Function"
        for event in resource["Properties"]["Events"].values()
    }
    integrations = {
        (
            path,
            re.search(
                r"\$\{(\w+)\.Arn\}",
                item["get"]["x-amazon-apigateway-integration"]["uri"]["Fn::Sub"],
            )[1],
        )
        for path, item in spec["paths"].items()
    }
    assert events == integrations
    assert len(events) == 13


def test_handlers_exist():
    template = load("template.yaml", CfnLoader)
    for name, resource in template["Resources"].items():
        if resource["Type"] != "AWS::Serverless::Function":
            continue
        props = resource["Properties"]
        module, handler = props["Handler"].rsplit(".", 1)
        path = os.path.join(REPO, props["CodeUri"], *module.split(".")) + ".py"
        with open(path, encoding="utf-8") as f:
            assert re.search(
                rf"^{handler} = ", f.read(), re.M
            ), f"{name}: {handler} not in {path}"


def test_apigateway_spec_has_no_examples_or_nulls(tmp_path):
    from scripts import apigateway_spec

    spec = apigateway_spec.without_examples(load("use-of-force-openapi.yaml"))
    assert apigateway_spec.null_paths(spec) == []
    text = yaml.safe_dump(spec)
    assert "example" not in text
    # The integrations API Gateway needs are still there
    assert text.count("x-amazon-apigateway-integration") == 13


def test_null_paths():
    from scripts import apigateway_spec

    assert apigateway_spec.null_paths({"a": [1, {"b": None}], "c": None}) == [
        "/a/1/b",
        "/c",
    ]
