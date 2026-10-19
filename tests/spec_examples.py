"""The example replies in the OpenAPI spec, as pytest parameters"""

import os
import re

import pytest
import yaml

REPO = os.path.join(os.path.dirname(__file__), "..")
SPEC = os.path.join(REPO, "use-of-force-openapi.yaml")


def load_examples():
    """pytest.param(resource, function, example) for every 200 example"""
    with open(SPEC, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    cases = []
    for path, item in spec["paths"].items():
        get = item["get"]
        function = re.search(
            r"\$\{(\w+)\.Arn\}",
            get["x-amazon-apigateway-integration"]["uri"]["Fn::Sub"],
        )[1]
        content = get["responses"]["200"]["content"]["application/vnd.api+json"]
        if "examples" in content:
            examples = {name: e["value"] for name, e in content["examples"].items()}
        else:
            examples = {"example": content["example"]}
        for name, example in examples.items():
            cases.append(pytest.param(path, function, example, id=f"{path} {name}"))
    return cases
