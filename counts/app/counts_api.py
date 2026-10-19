"""Handler for /counts/incidents and /counts/subjects"""

from uofapi import Reply, make_handler
from uofparams import (
    FILTER_PARAMS,
    PAGE_PARAMS,
    check_allowed,
    incident_filters,
    page_parameters,
)

from . import counts_lib as lib

ROOT = "/nj/use_of_force"


def make_route(endpoint):
    def route(path, query):
        check_allowed(query, ["by"] + FILTER_PARAMS + PAGE_PARAMS)
        dimensions = lib.parse_by(lib.get_data(), endpoint, query.get("by"))
        filters, link_params = incident_filters(query)
        records, aux = lib.get_counts(
            endpoint, dimensions, filters, page_parameters(query)
        )
        return Reply(records, aux, {**link_params, "by": query["by"]})

    return route


counts_handler = make_handler(
    {
        f"{ROOT}/counts/incidents": make_route("incidents"),
        f"{ROOT}/counts/subjects": make_route("subjects"),
    }
)
