"""Handler for /attributes, /attributes/{attribute}, its levels, and an incident's attribute rows"""

from uofapi import Reply, make_handler
from uofparams import (
    FILTER_PARAMS,
    PAGE_PARAMS,
    check_allowed,
    incident_filters,
    page_parameters,
    parse_int,
)

from . import attributes_lib as lib

ROOT = "/nj/use_of_force"


def codebook(path, query):
    check_allowed(query, [])
    return Reply(lib.get_codebook(lib.get_db()), {})


def attribute_rows(path, query):
    check_allowed(query, FILTER_PARAMS + PAGE_PARAMS)
    filters, link_params = incident_filters(query)
    records, aux = lib.get_attribute_rows(
        lib.get_db(), path["attribute"], filters, page_parameters(query)
    )
    return Reply(records, aux, link_params)


def levels(path, query):
    check_allowed(query, [])
    return Reply(lib.get_levels(lib.get_db(), path["attribute"]), {})


def incident_attribute_rows(path, query):
    check_allowed(query, PAGE_PARAMS)
    form_id = parse_int("form_id", path["form_id"])
    records, aux = lib.get_incident_attribute_rows(
        lib.get_db(), path["attribute"], form_id, page_parameters(query)
    )
    return Reply(records, aux)


attributes_handler = make_handler(
    {
        f"{ROOT}/attributes": codebook,
        f"{ROOT}/attributes/{{attribute}}": attribute_rows,
        f"{ROOT}/attributes/{{attribute}}/levels": levels,
        f"{ROOT}/incidents/{{form_id}}/attributes/{{attribute}}": incident_attribute_rows,
    }
)
