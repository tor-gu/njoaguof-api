"""Read-only access to a function's SQLite database (see scripts/build_data.py)"""

import os
import sqlite3

from uofparams import NotFound

DB_NAME = "njoaguof.sqlite"

# Filter -> incident column; text filters are matched through labels
FILTER_COLUMNS = {
    "agency": "agency_name",
    "agency_county": "agency_county",
    "incident_municipality": "incident_municipality",
    "incident_municipality_county": "incident_municipality_county",
}


class Database:
    """
    A read-only database, with the column storage and labels needed to turn
    stored rows back into API values
    """

    def __init__(self, data_dir):
        path = os.path.join(data_dir, DB_NAME)
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        # immutable: never changes while the function runs, so no locking
        self.con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        tables = {
            r[0]
            for r in self.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        self.storage = {}
        self.columns = {}
        if "columns" in tables:
            for table, column, storage in self.execute(
                'SELECT "table", "column", "storage" FROM columns ORDER BY "table", "position"'
            ):
                self.storage[(table, column)] = storage
                self.columns.setdefault(table, []).append(column)
        self.labels = {}
        if "labels" in tables:
            for table, column, code, label in self.execute(
                'SELECT "table", "column", "code", "label" FROM labels'
            ):
                self.labels.setdefault((table, column), {})[code] = label
        self.codes = {
            key: {label: code for code, label in labels.items()}
            for key, labels in self.labels.items()
        }

    def execute(self, sql, args=()):
        return self.con.execute(sql, args)

    def select_columns(self, table, alias=None):
        """SQL for the table's returned columns, in order"""
        prefix = f"{alias}." if alias else ""
        return ", ".join(f'{prefix}"{c}"' for c in self.columns[table])

    def decoder(self, table):
        """Function turning a stored row of select_columns(table) into a dict"""
        convert = []
        for column in self.columns[table]:
            storage = self.storage[(table, column)]
            if storage == "logical":
                convert.append(lambda v: None if v is None else bool(v))
            elif storage == "date":
                convert.append(
                    lambda v: (
                        None
                        if v is None
                        else f"{v // 10000:04d}-{v // 100 % 100:02d}-{v % 100:02d}"
                    )
                )
            elif storage == "code":
                labels = self.labels[(table, column)]
                convert.append(
                    lambda v, labels=labels: None if v is None else labels[v]
                )
            else:
                convert.append(lambda v: v)
        names = self.columns[table]
        return lambda row: {n: f(v) for n, f, v in zip(names, convert, row)}

    def filter_sql(self, filters, alias="incident"):
        """
        SQL conditions on the incident table for the filters.

        Returns:
            (sql, args), where sql is "" when there are no filters

        Raises:
            NotFound when a text filter matches no value at all
        """
        conditions, args = [], []
        date_range = filters.date_range()
        if date_range is not None:
            conditions.append(f'{alias}."incident_date_1" BETWEEN ? AND ?')
            args += list(date_range)
        for name, column in FILTER_COLUMNS.items():
            value = getattr(filters, name)
            if value is None:
                continue
            code = self.codes.get(("incident", column), {}).get(value)
            if code is None:
                raise NotFound(f"No incidents with {name} {value}")
            conditions.append(f'{alias}."{column}" = ?')
            args.append(code)
        if filters.officer_name_id is not None:
            conditions.append(f'{alias}."officer_name_id" = ?')
            args.append(filters.officer_name_id)
        return " AND ".join(conditions), args


def paged(db, select_sql, count_sql, args, page, convert=None):
    """
    One page of a query.

    Args:
        select_sql: the query, ordered, without LIMIT/OFFSET
        count_sql: a query returning the number of rows of select_sql
        args: the arguments of both
        page: dict with page_number and page_size
        convert: function applied to each row (default: none)

    Returns:
        list of records, aux dict for torguapi_make_links_and_meta

    Raises:
        NotFound when there are no rows, or the page is past the last one
    """
    record_count = db.execute(count_sql, args).fetchone()[0]
    page_number, page_size = page["page_number"], page["page_size"]
    if record_count == 0:
        raise NotFound("No matching records")
    page_count = (record_count - 1) // page_size + 1
    if page_number > page_count:
        raise NotFound(f"Page number {page_number} not found")
    rows = db.execute(
        f"{select_sql} LIMIT ? OFFSET ?",
        list(args) + [page_size, (page_number - 1) * page_size],
    ).fetchall()
    records = [convert(r) for r in rows] if convert else rows
    aux = {
        "page_number": page_number,
        "page_size": page_size,
        "record_count": record_count,
    }
    return records, aux
