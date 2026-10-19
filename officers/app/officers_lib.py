"""Officers and their name variants, from officers/data/njoaguof.sqlite"""

import os

from uofdb import Database
from uofparams import NotFound

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Opened on first use and kept while the function is warm
_db = None


def get_db():
    global _db
    if _db is None:
        _db = Database(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    return _db


def get_officer(db, officer_name_id):
    """The officer as a one-record list: {officer_name_id, officer_name, incident_count}"""
    row = db.execute(
        "SELECT officer_name_id, officer_name, incident_count FROM officer WHERE officer_name_id = ?",
        (officer_name_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"Officer {officer_name_id} not found")
    return [dict(zip(("officer_name_id", "officer_name", "incident_count"), row))]


def get_name_variants(db, officer_name_id):
    """The officer's name variants, in the order of the R package"""
    rows = db.execute(
        "SELECT officer_name_id, officer_name FROM officer_name_variants "
        "WHERE officer_name_id = ? ORDER BY rowid",
        (officer_name_id,),
    ).fetchall()
    if not rows:
        raise NotFound(f"Officer {officer_name_id} not found")
    return [dict(zip(("officer_name_id", "officer_name"), r)) for r in rows]
