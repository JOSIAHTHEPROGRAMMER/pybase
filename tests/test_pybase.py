import os
import sys
import shutil
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Database
from cli import (
    parse_create_table, parse_insert, parse_select,
    _detect_set_operator, resolve_subqueries
)


DATA_DIR = "data"


@pytest.fixture(autouse=True)
def fresh_db():
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR)
    yield
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)

    os.makedirs(DATA_DIR)



def make_db():
    db = Database()

    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE dept (id int PRIMARY KEY, name string NOT NULL)"
    )
    t = db.create_table(tn, cols)
    if pk: t.set_primary_key(pk)
    for col in nn: t.add_not_null_constraint(col)

    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE emp (id int PRIMARY KEY, dept_id int, name string, salary int)"
    )
    t = db.create_table(tn, cols)
    if pk: t.set_primary_key(pk)

    for sql in [
        "INSERT INTO dept VALUES (1, 'Engineering')",
        "INSERT INTO dept VALUES (2, 'Sales')",
        "INSERT INTO dept VALUES (3, 'HR')",
        "INSERT INTO emp VALUES (1, 1, 'Alice', 90000)",
        "INSERT INTO emp VALUES (2, 1, 'Bob',   80000)",
        "INSERT INTO emp VALUES (3, 2, 'Carol', 70000)",
        "INSERT INTO emp VALUES (4, 2, 'Dave',  70000)",
        "INSERT INTO emp VALUES (5, 3, 'Eve',   60000)",
    ]:
        tn, row = parse_insert(sql)
        db.get_table(tn).insert(row, db=db)

    return db


def sel(db, sql):
    set_op = _detect_set_operator(sql)
    if set_op:
        operator, left_sql, right_sql = set_op

        def one_side(s):
            t, sc, c, o, l, d, g, h = parse_select(s)
            resolve_subqueries(c, db)
            table = db.get_table(t)
            return table.select_aggregate(sc, c, g, h) if g else table.select_advanced(sc, c, o, l, distinct=d)

        left_rows  = one_side(left_sql)
        right_rows = one_side(right_sql)

        if operator == "UNION ALL":
            return left_rows + right_rows

        if operator == "UNION":
            seen, rows = [], []
            for row in left_rows + right_rows:
                if row not in seen:
                    seen.append(row)
                    rows.append(row)
            return rows

        if operator == "INTERSECT":
            seen, rows = [], []
            for row in left_rows:
                if row in right_rows and row not in seen:
                    seen.append(row)
                    rows.append(row)
            return rows

        if operator == "EXCEPT":
            seen, rows = [], []
            for row in left_rows:
                if row not in right_rows and row not in seen:
                    seen.append(row)
                    rows.append(row)
            return rows

    t, sc, c, o, l, d, g, h = parse_select(sql)
    resolve_subqueries(c, db)
    table = db.get_table(t)
    if g:
        return table.select_aggregate(sc, c, g, h)
    return table.select_advanced(sc, c, o, l, distinct=d)


def test_distinct_salary():
    db = make_db()
    rows = sel(db, "SELECT DISTINCT salary FROM emp")
    values = [r[0] for r in rows]
    assert len(values) == 4
    assert len(values) == len(set(values)), "DISTINCT should remove duplicates"


def test_distinct_dept_id():
    db = make_db()
    rows = sel(db, "SELECT DISTINCT dept_id FROM emp")
    values = [r[0] for r in rows]
    assert sorted(values) == [1, 2, 3]


def test_alias_parsing_columns():
    t, sc, c, o, l, d, g, h = parse_select(
        "SELECT id AS employee_id, name AS employee_name FROM emp"
    )
    assert sc == ["id", "name"], "aliases should be stripped, real column names returned"


def test_alias_parsing_table():
    t, sc, c, o, l, d, g, h = parse_select("SELECT id FROM emp AS e")
    assert t == "emp", "table alias should be stripped from table_name"


def test_group_by_count():
    db = make_db()
    rows = sel(db, "SELECT dept_id, COUNT(*) FROM emp GROUP BY dept_id")
    counts = {r[0]: r[1] for r in rows}
    assert counts == {1: 2, 2: 2, 3: 1}


def test_group_by_sum():
    db = make_db()
    rows = sel(db, "SELECT dept_id, SUM(salary) FROM emp GROUP BY dept_id")
    totals = {r[0]: r[1] for r in rows}
    assert totals == {1: 170000, 2: 140000, 3: 60000}


def test_group_by_avg():
    db = make_db()
    rows = sel(db, "SELECT dept_id, AVG(salary) FROM emp GROUP BY dept_id")
    avgs = {r[0]: r[1] for r in rows}
    assert avgs == {1: 85000.0, 2: 70000.0, 3: 60000.0}


def test_group_by_min_max():
    db = make_db()
    rows = sel(db, "SELECT dept_id, MIN(salary), MAX(salary) FROM emp GROUP BY dept_id")
    data = {r[0]: (r[1], r[2]) for r in rows}
    assert data[1] == (80000, 90000)
    assert data[2] == (70000, 70000)
    assert data[3] == (60000, 60000)


def test_having():
    db = make_db()
    rows = sel(db, "SELECT dept_id, COUNT(*) FROM emp GROUP BY dept_id HAVING COUNT(*) > 1")
    dept_ids = [r[0] for r in rows]
    assert sorted(dept_ids) == [1, 2], "only depts with more than one employee"


def test_union_deduplicates():
    db = make_db()
    rows = sel(db, "SELECT name FROM dept UNION SELECT name FROM emp")
    names = [r[0] for r in rows]
    assert len(names) == len(set(names)), "UNION should deduplicate"
    assert len(names) == 8


def test_union_all_keeps_duplicates():
    db = make_db()
    rows = sel(db, "SELECT dept_id FROM emp WHERE salary > 60000 UNION ALL SELECT dept_id FROM emp WHERE dept_id = 1")
    assert len(rows) == 6


def test_intersect_deduplicates():
    db = make_db()
    rows = sel(db, "SELECT dept_id FROM emp WHERE salary >= 70000 INTERSECT SELECT dept_id FROM emp WHERE dept_id = 2")
    values = [r[0] for r in rows]
    assert values == [2], "intersect should return only dept 2, deduplicated"


def test_except_deduplicates():
    db = make_db()
    rows = sel(db, "SELECT dept_id FROM emp EXCEPT SELECT dept_id FROM emp WHERE dept_id = 1")
    values = [r[0] for r in rows]
    assert 1 not in values
    assert len(values) == len(set(values)), "EXCEPT should deduplicate"
    assert sorted(values) == [2, 3]


def test_subquery_in():
    db = make_db()
    rows = sel(db, "SELECT name FROM emp WHERE dept_id IN (SELECT id FROM dept WHERE id < 3)")
    names = [r[0] for r in rows]
    assert sorted(names) == ["Alice", "Bob", "Carol", "Dave"]


def test_exists_subquery():
    db = make_db()
    rows = sel(db, "SELECT id FROM dept WHERE EXISTS (SELECT id FROM emp WHERE dept_id = 1)")
    assert len(rows) == 3, "EXISTS is true for all dept rows when subquery returns results"


def test_any_subquery():
    db = make_db()
    rows = sel(db, "SELECT name FROM emp WHERE salary > ANY (SELECT salary FROM emp WHERE dept_id = 3)")
    names = [r[0] for r in rows]
    assert sorted(names) == ["Alice", "Bob", "Carol", "Dave"]


def test_all_subquery():
    db = make_db()
    rows = sel(db, "SELECT name FROM emp WHERE salary > ALL (SELECT salary FROM emp WHERE dept_id = 3)")
    names = [r[0] for r in rows]
    assert sorted(names) == ["Alice", "Bob", "Carol", "Dave"]