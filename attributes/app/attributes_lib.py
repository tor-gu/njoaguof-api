"""Attributes: the codebook, levels and attribute rows, from attributes/data/njoaguof.sqlite"""

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


def get_codebook(db):
    """Every attribute, as {attribute, table, shape, value_column}, by attribute"""
    rows = db.execute(
        'SELECT attribute, "table", shape, value_column FROM attributes ORDER BY attribute'
    )
    return [dict(zip(("attribute", "table", "shape", "value_column"), r)) for r in rows]


def get_attribute(db, attribute):
    """(table, shape, value_column) of the attribute"""
    row = db.execute(
        'SELECT "table", shape, value_column FROM attributes WHERE attribute = ?',
        (attribute,),
    ).fetchone()
    if row is None:
        raise NotFound(f"Attribute {attribute} not found")
    return row


def get_levels(db, attribute):
    """The attribute's declared levels, as {attribute, position, level}"""
    get_attribute(db, attribute)
    rows = db.execute(
        "SELECT attribute, position, level FROM levels WHERE attribute = ? ORDER BY position",
        (attribute,),
    )
    return [dict(zip(("attribute", "position", "level"), r)) for r in rows]


def row_query(db, attribute):
    """SELECT and ORDER BY clauses for the attribute's rows, and a row converter"""
    table, shape, value_column = get_attribute(db, attribute)
    labels = dict(
        db.execute(
            "SELECT position, level FROM levels WHERE attribute = ?", (attribute,)
        )
    )
    if shape == "incident":
        select = f'SELECT form_id, code FROM "{table}"'
        order = "ORDER BY form_id, seq"

        def convert(r):
            return {"form_id": r[0], value_column: labels.get(r[1])}

    else:
        select = f'SELECT form_id, "index", code FROM "{table}"'
        order = 'ORDER BY form_id, "index"'

        def convert(r):
            return {"form_id": r[0], "index": r[1], value_column: labels.get(r[2])}

    return table, select, order, convert


def get_attribute_rows(db, attribute, filters, page):
    """The attribute's rows for the incidents matching the filters"""
    table, select, order, convert = row_query(db, attribute)
    conditions, args = db.filter_sql(filters)
    selected = ""
    if conditions:
        selected = f"WHERE form_id IN (SELECT form_id FROM incident WHERE {conditions})"
    return paged(
        db,
        f"{select} {selected} {order}",
        f'SELECT COUNT(*) FROM "{table}" {selected}',
        args,
        page,
        convert,
    )


def get_incident_attribute_rows(db, attribute, form_id, page):
    """The attribute's rows for one incident"""
    table, select, order, convert = row_query(db, attribute)
    if (
        db.execute("SELECT 1 FROM incident WHERE form_id = ?", (form_id,)).fetchone()
        is None
    ):
        raise NotFound(f"Incident {form_id} not found")
    return paged(
        db,
        f"{select} WHERE form_id = ? {order}",
        f'SELECT COUNT(*) FROM "{table}" WHERE form_id = ?',
        (form_id,),
        page,
        convert,
    )
