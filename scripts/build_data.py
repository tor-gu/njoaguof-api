"""
Build each function's data from the exported tables (make data).

Usage: python scripts/build_data.py [data dir] [repo root]

Reads data/ as written by scripts/export_data.R (<table>.csv[.gz],
columns.csv, levels.csv, SOURCE) and writes, under the repo root:

  incidents/data/njoaguof.sqlite    incident, subject, agency
  attributes/data/njoaguof.sqlite   the 16 attribute tables, an incident
                                    filter table, the codebook and the levels
  officers/data/njoaguof.sqlite     officer, officer_name_variants
  counts/data/                      int32 columns (*.i32) and labels.json

Only the standard library is used, so this runs anywhere Python 3.12 does.

Size matters (a cold start costs about 13 ms per zipped MB), so repeated
values are stored as integer codes:

  storage   stored as                         returned as
  integer   INTEGER                           int
  logical   INTEGER 0/1                       bool
  date      INTEGER yyyymmdd                  'YYYY-MM-DD'
  code      INTEGER, see the labels table     the label
  text      TEXT                              str

A code is a factor's level position, or a character column's position in
sorted order. In the counts columns 0 means null (and logicals are 1 = false,
2 = true); in SQLite null is NULL. Either way, sorting codes sorts values in
the order the API promises: declared levels, null last.

Rows keep the export's order, which is R's row order.
"""

import array
import csv
import gzip
import json
import os
import sqlite3
import sys
from collections import defaultdict

DB_NAME = "njoaguof.sqlite"

# Character columns stored as codes (many repeats); others stay text.
# officer_name stays text: with ~23k distinct names, its labels would cost
# more to load on a cold start (~130 ms at 512 MB) than the codes save.
CODED_CHARACTER = {
    ("incident", "agency_name"),
    ("incident", "incident_municipality"),
    ("incident", "officer_rank"),
}

# Incident columns the shared filters use (common_layer/uofdb.py)
FILTER_COLUMNS = [
    "incident_date_1",
    "agency_name",
    "agency_county",
    "incident_municipality",
    "incident_municipality_county",
    "officer_name_id",
]

# Their indexes. Each equality filter is indexed together with the date, so a
# filter plus a date range (year, start_date, end_date) is answered from the
# index alone ("covering"): counting the matches doesn't read incident rows,
# which on a cold Lambda means far fewer reads from disk (REVIEW §5b).
FILTER_INDEXES = [["incident_date_1"]] + [
    [c, "incident_date_1"] for c in FILTER_COLUMNS if c != "incident_date_1"
]

# Counts: incident columns stored as inc.<name>.i32 (besides form_id, date,
# year, month and officer_name_id), by source column
COUNT_INCIDENT_CODED = {
    "agency": "agency_name",
    "agency_county": "agency_county",
    "incident_municipality": "incident_municipality",
    "incident_municipality_county": "incident_municipality_county",
    "officer_gender": "officer_gender",
    "officer_race": "officer_race",
    "video_footage": "video_footage",
}
COUNT_SUBJECT_CODED = ["type", "race", "gender", "arrested", "juvenile", "injured"]


class BuildError(Exception):
    pass


# --- reading the export ---


def read_csv(path):
    """Header and rows of a .csv or .csv.gz file, as lists of strings"""
    if not os.path.exists(path) and os.path.exists(path + ".gz"):
        path = path + ".gz"
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        return header, list(reader)


def converter(type_):
    """Converts a CSV field of the given R type; an empty field is None"""
    if type_ == "integer":
        return lambda v: int(v) if v != "" else None
    if type_ == "logical":

        def logical(v):
            if v == "":
                return None
            if v not in ("TRUE", "FALSE"):
                raise BuildError(f"bad logical {v!r}")
            return v == "TRUE"

        return logical
    if type_ in ("date", "factor", "character"):
        return lambda v: v if v != "" else None
    raise BuildError(f"unknown column type {type_!r}")


class Export:
    """The exported tables, their column types, factor levels and SOURCE"""

    def __init__(self, data_dir):
        self.types = defaultdict(list)  # table -> [(column, R type)]
        _, rows = read_csv(os.path.join(data_dir, "columns.csv"))
        for table, _, column, type_ in sorted(rows, key=lambda r: (r[0], int(r[1]))):
            self.types[table].append((column, type_))

        self.levels = defaultdict(list)  # (table, column) -> [level]
        _, rows = read_csv(os.path.join(data_dir, "levels.csv"))
        for table, column, _, level in sorted(
            rows, key=lambda r: (r[0], r[1], int(r[2]))
        ):
            self.levels[(table, column)].append(level)

        self.tables = {}  # table -> [row dict]
        for table, cols in self.types.items():
            header, rows = read_csv(os.path.join(data_dir, f"{table}.csv"))
            names = [c for c, _ in cols]
            if header != names:
                raise BuildError(
                    f"{table}: header {header} doesn't match columns.csv {names}"
                )
            convs = [converter(t) for _, t in cols]
            self.tables[table] = [
                {n: conv(v) for n, conv, v in zip(names, convs, row)} for row in rows
            ]
            for column, type_ in cols:
                if type_ == "factor":
                    bad = {r[column] for r in self.tables[table]}
                    bad -= set(self.levels[(table, column)]) | {None}
                    if bad:
                        raise BuildError(
                            f"{table}.{column}: values not in levels: {sorted(bad)}"
                        )

        self.source = {}
        with open(os.path.join(data_dir, "SOURCE"), encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    key, value = line.rstrip("\n").split("=", 1)
                    self.source[key] = value

        for required in ("incident", "subject", "officer_name_variants"):
            if required not in self.tables:
                raise BuildError(f"{required} is missing from {data_dir}")
        self._labels = {}

    def type_of(self, table, column):
        return dict(self.types[table])[column]

    def storage(self, table, column):
        type_ = self.type_of(table, column)
        if type_ == "factor" or (table, column) in CODED_CHARACTER:
            return "code"
        return {"integer": "integer", "logical": "logical", "date": "date"}.get(
            type_, "text"
        )

    def labels(self, table, column):
        """The labels of a coded column; code i is labels[i - 1]"""
        key = (table, column)
        if key not in self._labels:
            if self.type_of(table, column) == "factor":
                self._labels[key] = list(self.levels[key])
            else:
                self._labels[key] = sorted(
                    {r[column] for r in self.tables[table]} - {None}
                )
        return self._labels[key]

    def codes(self, table, column):
        return {label: i for i, label in enumerate(self.labels(table, column), 1)}

    def stored(self, table, column):
        """Function mapping a value of the column to its SQLite value"""
        storage = self.storage(table, column)
        if storage == "code":
            code = self.codes(table, column)
            return lambda v: None if v is None else code[v]
        if storage == "date":
            return lambda v: None if v is None else int(v.replace("-", ""))
        if storage == "logical":
            return lambda v: None if v is None else int(v)
        return lambda v: v

    def attributes(self):
        """[(attribute, table, shape, value_column)], sorted by attribute"""
        out = []
        for table, cols in self.types.items():
            if not table.startswith("incident_"):
                continue
            names = [c for c, _ in cols]
            shape = (
                "incident_subject"
                if table.startswith("incident_subject_")
                else "incident"
            )
            keys = ["form_id", "index"] if shape == "incident_subject" else ["form_id"]
            if names[:-1] != keys:
                raise BuildError(f"{table}: unexpected columns {names}")
            if cols[-1][1] != "factor":
                raise BuildError(f"{table}: value column {names[-1]} is not a factor")
            out.append((table[len("incident_") :], table, shape, names[-1]))
        return sorted(out)


# --- SQLite ---

SQL_TYPE = {
    "integer": "INTEGER",
    "logical": "INTEGER",
    "date": "INTEGER",
    "code": "INTEGER",
}


def new_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    return sqlite3.connect(path)


def create_table(con, name, col_sql, rows, suffix=""):
    """col_sql: column definitions (and table constraints); rows: iterable of sequences"""
    con.execute(f'CREATE TABLE "{name}" ({", ".join(col_sql)}){suffix}')
    n_columns = sum(1 for c in col_sql if not c.startswith("PRIMARY KEY"))
    marks = ", ".join("?" * n_columns)
    con.executemany(f'INSERT INTO "{name}" VALUES ({marks})', rows)


def create_index(con, table, columns):
    name = f"{table}_{'_'.join(columns)}"
    col_sql = ", ".join(f'"{c}"' for c in columns)
    con.execute(f'CREATE INDEX "{name}" ON "{table}" ({col_sql})')


def finish_db(con, expected_counts):
    for table, expected in expected_counts.items():
        n = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if n != expected:
            raise BuildError(
                f"{table}: {n} rows in the database, {expected} in the export"
            )
    con.commit()
    con.execute("VACUUM")
    con.close()


def stored_table(con, ex, table, columns, key, without_rowid=False):
    """
    Writes columns of an exported table with their storage. key: the primary
    key column(s); a single integer key becomes the rowid.
    """
    col_sql = []
    for c in columns:
        sql_type = SQL_TYPE.get(ex.storage(table, c), "TEXT")
        pk = " PRIMARY KEY" if [c] == key and not without_rowid else ""
        col_sql.append(f'"{c}" {sql_type}{pk}')
    suffix = ""
    if without_rowid:
        col_sql.append("PRIMARY KEY (" + ", ".join(f'"{c}"' for c in key) + ")")
        suffix = " WITHOUT ROWID"
    stored = [ex.stored(table, c) for c in columns]
    create_table(
        con,
        table,
        col_sql,
        ([f(r[c]) for f, c in zip(stored, columns)] for r in ex.tables[table]),
        suffix,
    )


def labels_table(con, ex, columns):
    """labels(table, column, code, label) for the coded ones of [(table, column)]"""
    rows = []
    for table, column in columns:
        if ex.storage(table, column) == "code":
            rows += [
                (table, column, i, label)
                for i, label in enumerate(ex.labels(table, column), 1)
            ]
    create_table(
        con,
        "labels",
        [
            '"table" TEXT',
            '"column" TEXT',
            '"code" INTEGER',
            '"label" TEXT',
            'PRIMARY KEY ("table", "column", "code")',
        ],
        rows,
        " WITHOUT ROWID",
    )


def columns_table(con, ex, tables):
    """columns(table, position, column, storage): what each table returns, in order"""
    rows = [
        (t, i, c, ex.storage(t, c))
        for t in tables
        for i, (c, _) in enumerate(ex.types[t], 1)
    ]
    create_table(
        con,
        "columns",
        ['"table" TEXT', '"position" INTEGER', '"column" TEXT', '"storage" TEXT'],
        rows,
    )


def build_incidents(path, ex):
    con = new_db(path)
    inc_cols = [c for c, _ in ex.types["incident"]]
    subj_cols = [c for c, _ in ex.types["subject"]]
    stored_table(con, ex, "incident", inc_cols, ["form_id"])
    for columns in FILTER_INDEXES:
        create_index(con, "incident", columns)
    stored_table(
        con, ex, "subject", subj_cols, ["form_id", "index"], without_rowid=True
    )

    # /agencies, in output order: agency_name, then agency_county with null last
    counts = defaultdict(int)
    for r in ex.tables["incident"]:
        counts[(r["agency_name"], r["agency_county"])] += 1
    agencies = sorted(
        counts.items(), key=lambda kv: (kv[0][0], kv[0][1] is None, kv[0][1] or "")
    )
    create_table(
        con,
        "agency",
        ['"agency_name" TEXT', '"agency_county" TEXT', '"incident_count" INTEGER'],
        ([name, county, n] for (name, county), n in agencies),
    )

    columns_table(con, ex, ["incident", "subject"])
    labels_table(
        con,
        ex,
        [("incident", c) for c in inc_cols] + [("subject", c) for c in subj_cols],
    )
    finish_db(
        con,
        {"incident": len(ex.tables["incident"]), "subject": len(ex.tables["subject"])},
    )


def build_attributes(path, ex):
    con = new_db(path)
    attrs = ex.attributes()
    create_table(
        con,
        "attributes",
        ['"attribute" TEXT', '"table" TEXT', '"shape" TEXT', '"value_column" TEXT'],
        attrs,
    )
    level_rows = []
    expected = {}
    for attribute, table, shape, value_column in attrs:
        level_rows += [
            (attribute, i, lv) for i, lv in enumerate(ex.labels(table, value_column), 1)
        ]
        code = ex.codes(table, value_column)
        rows = ex.tables[table]
        if shape == "incident":
            # seq keeps the source order of an incident's values
            seq = defaultdict(int)
            out = []
            for r in rows:
                seq[r["form_id"]] += 1
                out.append((r["form_id"], seq[r["form_id"]], code.get(r[value_column])))
            if len({(f, c) for f, _, c in out}) != len(out):
                raise BuildError(f"{table}: repeated (form_id, {value_column}) rows")
            col_sql = [
                '"form_id" INTEGER',
                '"seq" INTEGER',
                '"code" INTEGER',
                'PRIMARY KEY ("form_id", "seq")',
            ]
        else:
            out = [(r["form_id"], r["index"], code.get(r[value_column])) for r in rows]
            col_sql = [
                '"form_id" INTEGER',
                '"index" INTEGER',
                '"code" INTEGER',
                'PRIMARY KEY ("form_id", "index")',
            ]
        create_table(con, table, col_sql, out, " WITHOUT ROWID")
        expected[table] = len(rows)
    create_table(
        con,
        "levels",
        ['"attribute" TEXT', '"position" INTEGER', '"level" TEXT'],
        level_rows,
    )

    # The incident columns the filters need, nothing else
    stored_table(con, ex, "incident", ["form_id"] + FILTER_COLUMNS, ["form_id"])
    for columns in FILTER_INDEXES:
        create_index(con, "incident", columns)
    labels_table(con, ex, [("incident", c) for c in FILTER_COLUMNS])
    expected["incident"] = len(ex.tables["incident"])
    finish_db(con, expected)


def build_officers(path, ex):
    con = new_db(path)
    names = defaultdict(set)
    counts = defaultdict(int)
    for r in ex.tables["incident"]:
        if r["officer_name_id"] is not None:
            names[r["officer_name_id"]].add(r["officer_name"])
            counts[r["officer_name_id"]] += 1
    several = [i for i, n in names.items() if len(n) != 1]
    if several:
        raise BuildError(f"officer_name_id with several standard names: {several[:10]}")
    create_table(
        con,
        "officer",
        [
            '"officer_name_id" INTEGER PRIMARY KEY',
            '"officer_name" TEXT',
            '"incident_count" INTEGER',
        ],
        ((i, next(iter(names[i])), counts[i]) for i in sorted(names)),
    )
    variants = ex.tables["officer_name_variants"]
    create_table(
        con,
        "officer_name_variants",
        ['"officer_name_id" INTEGER', '"officer_name" TEXT'],
        ((r["officer_name_id"], r["officer_name"]) for r in variants),
    )
    create_index(con, "officer_name_variants", ["officer_name_id"])
    finish_db(con, {"officer_name_variants": len(variants)})


# --- counts ---


def write_i32(path, values):
    with open(path, "wb") as f:
        array.array("i", values).tofile(f)


def build_counts(out_dir, ex):
    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(out_dir):
        if name.endswith(".i32") or name == "labels.json":
            os.remove(os.path.join(out_dir, name))
    labels = {}

    def coder(key, table, column):
        """Count codes for one column (0 = null); records its labels"""
        if ex.type_of(table, column) == "logical":
            return lambda v: 0 if v is None else (2 if v else 1)
        labels[key] = ex.labels(table, column)
        code = ex.codes(table, column)
        return lambda v: 0 if v is None else code[v]

    incident = sorted(ex.tables["incident"], key=lambda r: r["form_id"])
    dates = [int(r["incident_date_1"].replace("-", "")) for r in incident]
    inc_cols = {
        "form_id": [r["form_id"] for r in incident],
        "date": dates,
        "year": [d // 10000 for d in dates],
        "month": [d // 100 for d in dates],
        "officer_name_id": [r["officer_name_id"] or 0 for r in incident],
    }
    for dim, column in COUNT_INCIDENT_CODED.items():
        code = coder(f"incident.{dim}", "incident", column)
        inc_cols[dim] = [code(r[column]) for r in incident]
    for name, values in inc_cols.items():
        write_i32(os.path.join(out_dir, f"inc.{name}.i32"), values)

    row_of = {r["form_id"]: i for i, r in enumerate(incident)}
    subject = ex.tables["subject"]
    missing = {r["form_id"] for r in subject} - row_of.keys()
    if missing:
        raise BuildError(f"subjects of unknown incidents: {sorted(missing)[:10]}")
    write_i32(
        os.path.join(out_dir, "subj.inc_row.i32"),
        [row_of[r["form_id"]] for r in subject],
    )
    for column in COUNT_SUBJECT_CODED:
        code = coder(f"subject.{column}", "subject", column)
        write_i32(
            os.path.join(out_dir, f"subj.{column}.i32"),
            [code(r[column]) for r in subject],
        )

    for attribute, table, _, value_column in ex.attributes():
        code = coder(f"attribute.{attribute}", table, value_column)
        # Distinct (incident, value) pairs: an incident counts once per value
        pairs = sorted(
            {(row_of[r["form_id"]], code(r[value_column])) for r in ex.tables[table]}
        )
        write_i32(
            os.path.join(out_dir, f"a_{attribute}.row.i32"), [p[0] for p in pairs]
        )
        write_i32(os.path.join(out_dir, f"a_{attribute}.v.i32"), [p[1] for p in pairs])

    with open(os.path.join(out_dir, "labels.json"), "w", encoding="utf-8") as f:
        json.dump({"byteorder": sys.byteorder, "labels": labels}, f, ensure_ascii=False)


# --- main ---


def build_all(data_dir, root):
    ex = Export(data_dir)
    outputs = {
        "incidents": os.path.join(root, "incidents", "data", DB_NAME),
        "attributes": os.path.join(root, "attributes", "data", DB_NAME),
        "officers": os.path.join(root, "officers", "data", DB_NAME),
        "counts": os.path.join(root, "counts", "data"),
    }
    build_incidents(outputs["incidents"], ex)
    build_attributes(outputs["attributes"], ex)
    build_officers(outputs["officers"], ex)
    build_counts(outputs["counts"], ex)
    return outputs, ex.source


def size_of(path):
    if os.path.isdir(path):
        return sum(os.path.getsize(os.path.join(path, f)) for f in os.listdir(path))
    return os.path.getsize(path)


def main(argv):
    data_dir = argv[1] if len(argv) > 1 else "data"
    root = argv[2] if len(argv) > 2 else "."
    outputs, source = build_all(data_dir, root)
    print(
        f"Built from {source.get('package')} {source.get('version')} ({source.get('ref')})"
    )
    for name, path in outputs.items():
        print(f"  {name:10} {size_of(path) / 2**20:6.1f} MB  {path}")


if __name__ == "__main__":
    try:
        main(sys.argv)
    except BuildError as e:
        sys.exit(f"build_data: {e}")
