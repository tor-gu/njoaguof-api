"""Incidents, subjects and agencies, from incidents/data/njoaguof.sqlite"""

import os

from uofdb import Database, paged
from uofparams import NotFound

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Opened on first use and kept while the function is warm
_db = None


def get_db():
    global _db
    if _db is None:
        _db = Database(os.environ.get("DATA_DIR", DEFAULT_DATA_DIR))
    return _db


def where(conditions):
    return f"WHERE {conditions}" if conditions else ""


def get_incidents(db, filters, page):
    """Incidents matching the filters, ordered by form_id"""
    conditions, args = db.filter_sql(filters)
    return paged(
        db,
        f"SELECT {db.select_columns('incident')} FROM incident {where(conditions)} ORDER BY form_id",
        f"SELECT COUNT(*) FROM incident {where(conditions)}",
        args,
        page,
        db.decoder("incident"),
    )


def get_incident(db, form_id):
    """The incident as a one-record list"""
    row = db.execute(
        f"SELECT {db.select_columns('incident')} FROM incident WHERE form_id = ?",
        (form_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"Incident {form_id} not found")
    return [db.decoder("incident")(row)]


def get_incident_subjects(db, form_id, page):
    """The incident's subjects, ordered by index"""
    if (
        db.execute("SELECT 1 FROM incident WHERE form_id = ?", (form_id,)).fetchone()
        is None
    ):
        raise NotFound(f"Incident {form_id} not found")
    return paged(
        db,
        f'SELECT {db.select_columns("subject")} FROM subject WHERE form_id = ? ORDER BY "index"',
        "SELECT COUNT(*) FROM subject WHERE form_id = ?",
        (form_id,),
        page,
        db.decoder("subject"),
    )


def get_subjects(db, filters, page):
    """Subjects of the incidents matching the filters, ordered by form_id and index"""
    conditions, args = db.filter_sql(filters)
    selected = ""
    if conditions:
        selected = f"WHERE form_id IN (SELECT form_id FROM incident WHERE {conditions})"
    return paged(
        db,
        f'SELECT {db.select_columns("subject")} FROM subject {selected} ORDER BY form_id, "index"',
        f"SELECT COUNT(*) FROM subject {selected}",
        args,
        page,
        db.decoder("subject"),
    )


def get_agencies(db, page):
    """(agency_name, agency_county, incident_count), in the order built"""
    return paged(
        db,
        "SELECT agency_name, agency_county, incident_count FROM agency ORDER BY rowid",
        "SELECT COUNT(*) FROM agency",
        (),
        page,
        lambda r: {"agency_name": r[0], "agency_county": r[1], "incident_count": r[2]},
    )
