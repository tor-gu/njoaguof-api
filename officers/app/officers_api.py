"""Handler for /officers/{officer_name_id} and its name variants"""

from uofapi import Reply, make_handler
from uofparams import check_allowed, parse_int

from . import officers_lib as lib

ROOT = "/nj/use_of_force"


def officer(path, query):
    check_allowed(query, [])
    officer_name_id = parse_int("officer_name_id", path["officer_name_id"])
    return Reply(lib.get_officer(lib.get_db(), officer_name_id), {})


def name_variants(path, query):
    check_allowed(query, [])
    officer_name_id = parse_int("officer_name_id", path["officer_name_id"])
    return Reply(lib.get_name_variants(lib.get_db(), officer_name_id), {})


officers_handler = make_handler(
    {
        f"{ROOT}/officers/{{officer_name_id}}": officer,
        f"{ROOT}/officers/{{officer_name_id}}/name_variants": name_variants,
    }
)
