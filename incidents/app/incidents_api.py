"""Handler for /incidents, /incidents/{form_id}, its subjects, /subjects and /agencies"""

from uofapi import Reply, make_handler
from uofparams import (
    FILTER_PARAMS,
    PAGE_PARAMS,
    check_allowed,
    incident_filters,
    page_parameters,
    parse_int,
)

from . import incidents_lib as lib

ROOT = "/nj/use_of_force"


def incidents(path, query):
    check_allowed(query, FILTER_PARAMS + PAGE_PARAMS)
    filters, link_params = incident_filters(query)
    records, aux = lib.get_incidents(lib.get_db(), filters, page_parameters(query))
    return Reply(records, aux, link_params)


def incident(path, query):
    check_allowed(query, [])
    form_id = parse_int("form_id", path["form_id"])
    return Reply(lib.get_incident(lib.get_db(), form_id), {})


def incident_subjects(path, query):
    check_allowed(query, PAGE_PARAMS)
    form_id = parse_int("form_id", path["form_id"])
    records, aux = lib.get_incident_subjects(
        lib.get_db(), form_id, page_parameters(query)
    )
    return Reply(records, aux)


def subjects(path, query):
    check_allowed(query, FILTER_PARAMS + PAGE_PARAMS)
    filters, link_params = incident_filters(query)
    records, aux = lib.get_subjects(lib.get_db(), filters, page_parameters(query))
    return Reply(records, aux, link_params)


def agencies(path, query):
    check_allowed(query, PAGE_PARAMS)
    records, aux = lib.get_agencies(lib.get_db(), page_parameters(query))
    return Reply(records, aux)


incidents_handler = make_handler(
    {
        f"{ROOT}/incidents": incidents,
        f"{ROOT}/incidents/{{form_id}}": incident,
        f"{ROOT}/incidents/{{form_id}}/subjects": incident_subjects,
        f"{ROOT}/subjects": subjects,
        f"{ROOT}/agencies": agencies,
    }
)
