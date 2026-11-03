export PYTHONPATH = common_layer
export AWS_SAM_STACK_NAME ?= NjoaguofApiDev

# The local venv when there is one (make venv); CI has none and uses python
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

src_dirs := common_layer incidents attributes officers counts scripts tests

style:
	$(PYTHON) -m isort --profile black $(src_dirs)
	$(PYTHON) -m black --target-version py312 $(src_dirs)
	$(PYTHON) -m flake8 --ignore E501,E203,W503 $(src_dirs)

unit_test:
	$(PYTHON) -m pytest -sv tests/unit

# The spec's example replies, reproduced from the full data (needs make data)
example_test:
	$(PYTHON) -m pytest -sv tests/examples

integration_test:
	$(PYTHON) -m pytest -sv tests/integration

# The local venv (.venv, Python 3.12 as in CI and on Lambda)
venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

# Export the njoaguof tables from a tagged release, e.g. make export_data REF=v2.1.2
export_data:
	@test -n "$(REF)" || (echo "Usage: make export_data REF=<njoaguof git ref>" && exit 1)
	Rscript scripts/export_data.R $(REF)

# Build each function's data (<function>/data/) from data/
data:
	$(PYTHON) scripts/build_data.py data .

# The spec as template.yaml gives it to API Gateway (without examples)
apigateway_spec:
	$(PYTHON) scripts/apigateway_spec.py use-of-force-openapi.yaml apigateway-openapi.yaml

.PHONY: venv style unit_test example_test integration_test export_data data apigateway_spec

all: style unit_test data example_test
