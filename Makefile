export PYTHONPATH = common_layer
export AWS_SAM_STACK_NAME ?= NjoaguofApiDev

src_dirs := common_layer incidents attributes officers counts scripts tests

style:
	python -m isort --profile black $(src_dirs)
	python -m black --target-version py312 $(src_dirs)
	python -m flake8 --ignore E501,E203,W503 $(src_dirs)

unit_test:
	python -m pytest -sv tests/unit

# The spec's example replies, reproduced from the full data (needs make data)
example_test:
	python -m pytest -sv tests/examples

integration_test:
	python -m pytest -sv tests/integration

# Export the njoaguof tables from a tagged release, e.g. make export_data REF=v2.1.2
export_data:
	@test -n "$(REF)" || (echo "Usage: make export_data REF=<njoaguof git ref>" && exit 1)
	Rscript scripts/export_data.R $(REF)

# Build each function's data (<function>/data/) from data/
data:
	python scripts/build_data.py data .

.PHONY: style unit_test example_test integration_test export_data data

all: style unit_test data example_test
