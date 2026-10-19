"""Lambda handlers: route an API Gateway event and build the torguapi reply"""

import traceback
from dataclasses import dataclass
from http import HTTPStatus

from uofparams import InvalidRequest, NotFound, path_parameters, query_parameters

from torguapi import torguapi_http_error, torguapi_make_links_and_meta, torguapi_result


@dataclass
class Reply:
    """
    What a route returns.

    records: list of dicts
    aux: for torguapi_make_links_and_meta; without page_number, the links
        have only "self" and there is no meta (single-record replies)
    query_params: the checked query parameters to carry in the links
    """

    records: list
    aux: dict
    query_params: dict | None = None


def make_handler(routes):
    """
    Returns a Lambda handler for routes, a dict of API Gateway resource
    (e.g. "/nj/use_of_force/incidents/{form_id}") -> function(path, query)
    returning a Reply. path and query are the event's parameters as dicts.
    """

    def handler(event, context):
        resource = event.get("resource")
        route = routes.get(resource)
        if route is None:
            return torguapi_http_error(HTTPStatus.NOT_FOUND, f"No route for {resource}")
        path = path_parameters(event)
        query = query_parameters(event)
        try:
            reply = route(path, query)
            url_path = resource.format(**path).lstrip("/")
            links, meta = torguapi_make_links_and_meta(
                reply.aux, url_path, reply.query_params
            )
            return torguapi_result(reply.records, links, meta)
        except InvalidRequest as e:
            return torguapi_http_error(HTTPStatus.BAD_REQUEST, str(e))
        except NotFound as e:
            return torguapi_http_error(HTTPStatus.NOT_FOUND, str(e))
        except Exception:
            traceback.print_exc()
            return torguapi_http_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error"
            )

    return handler
