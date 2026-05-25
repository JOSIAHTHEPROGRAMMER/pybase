import os
import sys
import shutil
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Database
from cli import (
    parse_create_table, parse_insert, parse_select,
    parse_delete, parse_update, parse_alter_table,
    parse_truncate, parse_rename_table, parse_create_view,
    parse_drop_view, parse_explain, _detect_set_operator,
    resolve_subqueries
)
from query.planner import QueryPlanner
from query.executor import QueryExecutor
from query.utils import _has_aggregate


DATA_DIR = "data"


@pytest.fixture(autouse=True)
def clean_data():
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR)
    yield


def make_db():
    db = Database()

    for sql in [
        "CREATE TABLE dept (id int PRIMARY KEY, name string NOT NULL)",
        "CREATE TABLE emp (id int PRIMARY KEY AUTO_INCREMENT, dept_id int, name string NOT NULL, salary int DEFAULT 50000)",
        "CREATE TABLE orders (id int PRIMARY KEY AUTO_INCREMENT, emp_id int REFERENCES emp(id) ON DELETE CASCADE, amount int CHECK (amount > 0))",
    ]:
        tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(sql)
        t = db.create_table(tn, cols)
        if pk: t.set_primary_key(pk)
        for col in nn: t.add_not_null_constraint(col)
        for col, val in dv.items(): t.set_default_value(col, val)
        for cc_item in cc: t.add_check_constraint(cc_item["column"], cc_item["op"], cc_item["value"])
        for fk in fks:
            t.add_foreign_key(fk["column"], fk["ref_table"], fk["ref_column"],
                              on_delete=fk.get("on_delete"), on_update=fk.get("on_update"))
        if ai: t.set_auto_increment(ai)

    for sql in [
        "INSERT INTO dept VALUES (1, 'Engineering')",
        "INSERT INTO dept VALUES (2, 'Sales')",
        "INSERT INTO dept VALUES (3, 'HR')",
        "INSERT INTO emp VALUES (NULL, 1, 'Alice', 90000)",
        "INSERT INTO emp VALUES (NULL, 1, 'Bob', 80000)",
        "INSERT INTO emp VALUES (NULL, 2, 'Carol', 70000)",
        "INSERT INTO emp VALUES (NULL, 2, 'Dave', 70000)",
        "INSERT INTO emp VALUES (NULL, 3, 'Eve', 60000)",
        "INSERT INTO emp VALUES (NULL, NULL, 'Frank', 50000)",
        "INSERT INTO orders VALUES (NULL, 1, 500)",
        "INSERT INTO orders VALUES (NULL, 1, 200)",
        "INSERT INTO orders VALUES (NULL, 2, 300)",
    ]:
        tn, row = parse_insert(sql)
        db.get_table(tn).insert(row, db=db)

    return db


def sel(db, sql):
    set_op = _detect_set_operator(sql)
    if set_op:
        operator, left_sql, right_sql = set_op

        def one_side(s):
            t, sc, c, o, l, d, g, h, j, am = parse_select(s)
            if t in db.views:
                t, sc, c, o, l, d, g, h, j, am = parse_select(db.views[t])
            resolve_subqueries(c, db)
            if j:
                plan = QueryPlanner.build(j, sc, c, o, l, d)
                rows, _, _ = QueryExecutor(db).execute(plan)
                return rows
            return db.get_table(t).select_aggregate(sc, c, g, h) if (g or _has_aggregate(sc)) else db.get_table(t).select_advanced(sc, c, o, l, distinct=d)

        left_rows  = one_side(left_sql)
        right_rows = one_side(right_sql)

        if operator == "UNION ALL":
            return left_rows + right_rows
        if operator == "UNION":
            seen, rows = [], []
            for row in left_rows + right_rows:
                if row not in seen:
                    seen.append(row); rows.append(row)
            return rows
        if operator == "INTERSECT":
            seen, rows = [], []
            for row in left_rows:
                if row in right_rows and row not in seen:
                    seen.append(row); rows.append(row)
            return rows
        if operator == "EXCEPT":
            seen, rows = [], []
            for row in left_rows:
                if row not in right_rows and row not in seen:
                    seen.append(row); rows.append(row)
            return rows

    t, sc, c, o, l, d, g, h, j, am = parse_select(sql)
    if t in db.views:
        t, sc, c, o, l, d, g, h, j, am = parse_select(db.views[t])
    resolve_subqueries(c, db)
    if j:
        plan = QueryPlanner.build(j, sc, c, o, l, d)
        rows, col_names, _ = QueryExecutor(db).execute(plan)
        return rows
    if g or _has_aggregate(sc):
        return db.get_table(t).select_aggregate(sc, c, g, h)
    return db.get_table(t).select_advanced(sc, c, o, l, distinct=d)


def test_basic_insert_and_select():
    db = make_db()
    rows = sel(db, "SELECT * FROM dept")
    print(f"\n  all dept rows: {rows}")
    assert len(rows) == 3


def test_primary_key_not_null():
    db = make_db()
    with pytest.raises(ValueError):
        db.get_table("dept").insert([None, "Test"], db=db)
    print("\n  PRIMARY KEY NULL correctly rejected")


def test_not_null_constraint():
    db = make_db()
    with pytest.raises(ValueError):
        db.get_table("emp").insert([None, 1, None, 80000], db=db)
    print("\n  NOT NULL constraint correctly enforced")


def test_default_value():
    db = make_db()
    emp = db.get_table("emp")
    emp.insert([None, 1, 'Grace', None], db=db)
    rows = sel(db, "SELECT * FROM emp WHERE name = 'Grace'")
    salary = rows[0][3]
    print(f"\n  default salary applied: {salary}")
    assert salary == 50000


def test_check_constraint():
    db = make_db()
    with pytest.raises(ValueError):
        db.get_table("orders").insert([None, 1, -100], db=db)
    print("\n  CHECK constraint correctly rejected negative amount")


def test_auto_increment():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp")
    ids = [r[0] for r in rows]
    print(f"\n  auto increment ids: {ids}")
    assert ids == list(range(1, len(ids) + 1))


def test_unique_constraint():
    db = make_db()
    db.get_table("dept").add_unique_constraint("name")
    with pytest.raises(ValueError):
        db.get_table("dept").insert([4, "Engineering"], db=db)
    print("\n  UNIQUE constraint correctly rejected duplicate name")


def test_foreign_key_enforcement():
    db = make_db()
    with pytest.raises(ValueError):
        db.get_table("orders").insert([None, 999, 100], db=db)
    print("\n  FK violation correctly rejected")


def test_on_delete_cascade():
    db = make_db()
    orders_before = len(db.get_table("orders").rows)
    db.get_table("emp").delete([{"type": "simple", "column": "id", "op": "=", "value": 1}], db=db)
    orders_after = len(db.get_table("orders").rows)
    print(f"\n  orders before: {orders_before}, after cascade delete: {orders_after}")
    assert orders_after == orders_before - 2


def test_composite_primary_key():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE pivot (a int, b int)"
    )
    t = db.create_table(tn, cols)
    t.set_composite_primary_key(["a", "b"])
    t.insert([1, 2], db=db)
    with pytest.raises(ValueError):
        t.insert([1, 2], db=db)
    print("\n  composite PRIMARY KEY duplicate correctly rejected")


def test_where_comparison():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp WHERE salary > 70000")
    names = [r[2] for r in rows]
    print(f"\n  employees with salary > 70000: {names}")
    assert sorted(names) == ["Alice", "Bob"]


def test_where_between():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp WHERE salary BETWEEN 60000 AND 80000")
    print(f"\n  employees with salary BETWEEN 60000 AND 80000: {[r[2] for r in rows]}")
    assert len(rows) == 4


def test_where_like():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp WHERE name LIKE 'A%'")
    print(f"\n  employees with name LIKE A%: {[r[2] for r in rows]}")
    assert [r[2] for r in rows] == ["Alice"]


def test_where_is_null():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp WHERE dept_id IS NULL")
    print(f"\n  employees with NULL dept_id: {[r[2] for r in rows]}")
    assert [r[2] for r in rows] == ["Frank"]


def test_where_in():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp WHERE dept_id IN (1, 2)")
    print(f"\n  employees in dept 1 or 2: {[r[2] for r in rows]}")
    assert len(rows) == 4


def test_where_arithmetic():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp WHERE salary + 10000 > 90000")
    names = [r[2] for r in rows]
    print(f"\n  salary + 10000 > 90000: {names}")
    assert names == ["Alice"]


def test_order_by_asc():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp WHERE dept_id = 1 ORDER BY salary ASC")
    salaries = [r[3] for r in rows]
    print(f"\n  salaries ASC: {salaries}")
    assert salaries == sorted(salaries)


def test_order_by_desc():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp ORDER BY salary DESC")
    salaries = [r[3] for r in rows]
    print(f"\n  salaries DESC: {salaries}")
    assert salaries == sorted(salaries, reverse=True)


def test_multi_column_order_by():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp WHERE dept_id IS NOT NULL ORDER BY dept_id ASC, salary DESC")
    print(f"\n  multi-column ORDER BY dept_id ASC salary DESC:")
    for r in rows: print(f"    {r}")
    dept1 = [r for r in rows if r[1] == 1]
    assert dept1[0][3] >= dept1[-1][3]


def test_limit():
    db = make_db()
    rows = sel(db, "SELECT * FROM emp LIMIT 3")
    print(f"\n  LIMIT 3 returned {len(rows)} rows")
    assert len(rows) == 3


def test_distinct():
    db = make_db()
    rows = sel(db, "SELECT DISTINCT dept_id FROM emp")
    values = [r[0] for r in rows]
    print(f"\n  DISTINCT dept_id: {values}")
    assert len(values) == len(set(str(v) for v in values))


def test_column_alias():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT name AS employee, salary AS pay FROM emp")
    print(f"\n  alias_map: {am}")
    assert am == {"name": "employee", "salary": "pay"}
    assert sc == ["name", "salary"]


def test_count_all():
    db = make_db()
    rows = sel(db, "SELECT COUNT(*) FROM emp")
    print(f"\n  COUNT(*): {rows[0][0]}")
    assert rows[0][0] == 6


def test_count_distinct():
    db = make_db()
    rows = sel(db, "SELECT COUNT(DISTINCT dept_id) FROM emp")
    print(f"\n  COUNT(DISTINCT dept_id): {rows[0][0]}")
    assert rows[0][0] == 3


def test_sum():
    db = make_db()
    rows = sel(db, "SELECT SUM(salary) FROM emp")
    print(f"\n  SUM(salary): {rows[0][0]}")
    assert rows[0][0] == 420000


def test_avg():
    db = make_db()
    rows = sel(db, "SELECT AVG(salary) FROM emp")
    print(f"\n  AVG(salary): {rows[0][0]}")
    assert rows[0][0] == 70000.0


def test_min_max():
    db = make_db()
    rows = sel(db, "SELECT MIN(salary), MAX(salary) FROM emp")
    print(f"\n  MIN: {rows[0][0]}, MAX: {rows[0][1]}")
    assert rows[0][0] == 50000
    assert rows[0][1] == 90000


def test_group_by_count():
    db = make_db()
    rows = sel(db, "SELECT dept_id, COUNT(*) FROM emp GROUP BY dept_id")
    counts = {r[0]: r[1] for r in rows}
    print(f"\n  GROUP BY dept_id COUNT: {counts}")
    assert counts[1] == 2
    assert counts[2] == 2
    assert counts[3] == 1


def test_having():
    db = make_db()
    rows = sel(db, "SELECT dept_id, COUNT(*) FROM emp GROUP BY dept_id HAVING COUNT(*) > 1")
    dept_ids = sorted([r[0] for r in rows])
    print(f"\n  HAVING COUNT > 1: {dept_ids}")
    assert dept_ids == [1, 2]


def test_union():
    db = make_db()
    rows = sel(db, "SELECT name FROM dept UNION SELECT name FROM emp")
    names = [r[0] for r in rows]
    print(f"\n  UNION dept and emp names: {names}")
    assert len(names) == len(set(names))
    assert len(names) == 9


def test_union_all():
    db = make_db()
    rows = sel(db, "SELECT dept_id FROM emp WHERE salary > 70000 UNION ALL SELECT dept_id FROM emp WHERE dept_id = 1")
    print(f"\n  UNION ALL rows: {len(rows)}")
    assert len(rows) == 4


def test_intersect():
    db = make_db()
    rows = sel(db, "SELECT dept_id FROM emp WHERE salary >= 70000 INTERSECT SELECT dept_id FROM emp WHERE dept_id = 2")
    values = [r[0] for r in rows]
    print(f"\n  INTERSECT: {values}")
    assert values == [2]


def test_except():
    db = make_db()
    rows = sel(db, "SELECT dept_id FROM emp EXCEPT SELECT dept_id FROM emp WHERE dept_id = 1")
    values = [r[0] for r in rows]
    print(f"\n  EXCEPT dept 1: {values}")
    assert 1 not in values


def test_subquery_in():
    db = make_db()
    rows = sel(db, "SELECT name FROM emp WHERE dept_id IN (SELECT id FROM dept WHERE id < 3)")
    names = sorted([r[0] for r in rows])
    print(f"\n  subquery IN: {names}")
    assert names == ["Alice", "Bob", "Carol", "Dave"]


def test_exists_subquery():
    db = make_db()
    rows = sel(db, "SELECT id FROM dept WHERE EXISTS (SELECT id FROM emp WHERE dept_id = 1)")
    print(f"\n  EXISTS subquery returned {len(rows)} dept rows")
    assert len(rows) == 3


def test_any_subquery():
    db = make_db()
    rows = sel(db, "SELECT name FROM emp WHERE salary > ANY (SELECT salary FROM emp WHERE dept_id = 3)")
    names = sorted([r[0] for r in rows])
    print(f"\n  ANY subquery: {names}")
    assert "Eve" not in names
    assert "Alice" in names


def test_all_subquery():
    db = make_db()
    rows = sel(db, "SELECT name FROM emp WHERE salary > ALL (SELECT salary FROM emp WHERE dept_id = 3)")
    names = sorted([r[0] for r in rows])
    print(f"\n  ALL subquery: {names}")
    assert sorted(names) == ["Alice", "Bob", "Carol", "Dave"]


def test_inner_join():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM emp INNER JOIN dept ON emp.dept_id = dept.id")
    plan = QueryPlanner.build(j, sc, c, o, l, d)
    rows, col_names, _ = QueryExecutor(db).execute(plan)
    print(f"\n  INNER JOIN rows: {len(rows)}")
    assert len(rows) == 5
    emp_names = [r[col_names.index("emp.name")] for r in rows]
    assert "Frank" not in emp_names


def test_left_join():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM emp LEFT JOIN dept ON emp.dept_id = dept.id")
    plan = QueryPlanner.build(j, sc, c, o, l, d)
    rows, col_names, _ = QueryExecutor(db).execute(plan)
    print(f"\n  LEFT JOIN rows: {len(rows)}")
    assert len(rows) == 6
    frank = [r for r in rows if r[col_names.index("emp.name")] == "Frank"]
    assert frank[0][col_names.index("dept.name")] is None


def test_right_join():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM dept RIGHT JOIN emp ON dept.id = emp.dept_id")
    plan = QueryPlanner.build(j, sc, c, o, l, d)
    rows, col_names, _ = QueryExecutor(db).execute(plan)
    print(f"\n  RIGHT JOIN rows: {len(rows)}")
    assert len(rows) == 6


def test_full_outer_join():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM emp FULL OUTER JOIN dept ON emp.dept_id = dept.id")
    plan = QueryPlanner.build(j, sc, c, o, l, d)
    rows, col_names, _ = QueryExecutor(db).execute(plan)
    print(f"\n  FULL OUTER JOIN rows: {len(rows)}")
    assert len(rows) >= 6


def test_cross_join():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM dept CROSS JOIN orders")
    plan = QueryPlanner.build(j, sc, c, o, l, d)
    rows, _, _ = QueryExecutor(db).execute(plan)
    print(f"\n  CROSS JOIN 3 dept x 3 orders = {len(rows)} rows")
    assert len(rows) == 9


def test_self_join():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM emp AS a INNER JOIN emp AS b ON a.dept_id = b.dept_id")
    plan = QueryPlanner.build(j, sc, c, o, l, d)
    rows, col_names, _ = QueryExecutor(db).execute(plan)
    print(f"\n  SELF JOIN same dept pairs: {len(rows)}")
    for r in rows:
        assert r[col_names.index("a.dept_id")] == r[col_names.index("b.dept_id")]


def test_transaction_commit():
    db = make_db()
    db.begin_transaction()
    tn, row = parse_insert("INSERT INTO dept VALUES (4, 'Finance')")
    db.current_transaction.add("insert", tn, row=row)
    db.commit_transaction()
    rows = sel(db, "SELECT * FROM dept WHERE id = 4")
    print(f"\n  committed row: {rows}")
    assert len(rows) == 1


def test_transaction_rollback():
    db = make_db()
    db.begin_transaction()
    tn, row = parse_insert("INSERT INTO dept VALUES (4, 'Finance')")
    db.current_transaction.add("insert", tn, row=row)
    db.rollback_transaction()
    rows = sel(db, "SELECT * FROM dept WHERE id = 4")
    print(f"\n  rolled back, row should not exist: {rows}")
    assert len(rows) == 0


def test_savepoint():
    db = make_db()
    db.begin_transaction()
    tn, row = parse_insert("INSERT INTO dept VALUES (4, 'Finance')")
    db.current_transaction.add("insert", tn, row=row)
    db.current_transaction.savepoint("sp1")
    tn, row = parse_insert("INSERT INTO dept VALUES (5, 'Legal')")
    db.current_transaction.add("insert", tn, row=row)
    db.current_transaction.rollback_to_savepoint("sp1")
    db.commit_transaction()
    rows = sel(db, "SELECT * FROM dept")
    ids = [r[0] for r in rows]
    print(f"\n  after savepoint rollback dept ids: {ids}")
    assert 4 in ids
    assert 5 not in ids


def test_update():
    db = make_db()
    tn, assignments, conditions = parse_update("UPDATE emp SET salary = 99000 WHERE id = 1")
    db.get_table(tn).update(assignments, conditions, db=db)
    rows = sel(db, "SELECT * FROM emp WHERE id = 1")
    print(f"\n  updated salary: {rows[0][3]}")
    assert rows[0][3] == 99000


def test_delete():
    db = make_db()
    tn, conditions = parse_delete("DELETE FROM emp WHERE id = 6")
    db.get_table(tn).delete(conditions, db=db)
    rows = sel(db, "SELECT * FROM emp")
    names = [r[2] for r in rows]
    print(f"\n  after delete Frank: {names}")
    assert "Frank" not in names


def test_create_index():
    db = make_db()
    msg = db.get_table("emp").create_index("salary")
    print(f"\n  {msg}")
    assert "salary" in msg


def test_alter_add_column():
    db = make_db()
    db.get_table("emp").alter_add_column("bonus", "int", default=0)
    rows = sel(db, "SELECT * FROM emp")
    print(f"\n  after ADD COLUMN bonus, first row: {rows[0]}")
    assert len(rows[0]) == 5
    assert rows[0][4] == 0


def test_alter_drop_column():
    db = make_db()
    db.get_table("emp").alter_add_column("bonus", "int", default=0)
    db.get_table("emp").alter_drop_column("bonus")
    rows = sel(db, "SELECT * FROM emp")
    print(f"\n  after DROP COLUMN bonus, first row: {rows[0]}")
    assert len(rows[0]) == 4


def test_alter_rename_column():
    db = make_db()
    db.get_table("emp").alter_rename_column("salary", "pay")
    cols = [c[0] for c in db.get_table("emp").columns]
    print(f"\n  columns after RENAME: {cols}")
    assert "pay" in cols
    assert "salary" not in cols


def test_truncate():
    db = make_db()
    db.get_table("orders").truncate()
    rows = sel(db, "SELECT * FROM orders")
    print(f"\n  after TRUNCATE orders: {len(rows)} rows")
    assert len(rows) == 0
    assert db.get_table("orders").columns


def test_truncate_resets_auto_increment():
    db = make_db()
    db.get_table("orders").truncate()
    db.get_table("orders").insert([None, 1, 100], db=db)
    rows = sel(db, "SELECT * FROM orders")
    print(f"\n  after truncate and reinsert, id: {rows[0][0]}")
    assert rows[0][0] == 1


def test_rename_table():
    db = make_db()
    db.rename_table("orders", "purchases")
    assert "purchases" in db.tables
    assert "orders" not in db.tables
    rows = sel(db, "SELECT * FROM purchases")
    print(f"\n  renamed orders to purchases, {len(rows)} rows")
    assert len(rows) == 3


def test_create_view():
    db = make_db()
    db.create_view("high_earners", "SELECT name, salary FROM emp WHERE salary > 70000")
    assert "high_earners" in db.views
    rows = sel(db, "SELECT * FROM high_earners")
    names = sorted([r[0] for r in rows])
    print(f"\n  view high_earners: {names}")
    assert names == ["Alice", "Bob"]


def test_view_reflects_live_data():
    db = make_db()
    db.create_view("high_earners", "SELECT name, salary FROM emp WHERE salary > 70000")
    db.get_table("emp").insert([None, 1, "Grace", 95000], db=db)
    rows = sel(db, "SELECT * FROM high_earners")
    names = sorted([r[0] for r in rows])
    print(f"\n  view after insert Grace: {names}")
    assert "Grace" in names


def test_create_or_replace_view():
    db = make_db()
    db.create_view("high_earners", "SELECT name, salary FROM emp WHERE salary > 70000")
    db.create_view("high_earners", "SELECT name, salary FROM emp WHERE salary > 60000", replace=True)
    rows = sel(db, "SELECT * FROM high_earners")
    names = sorted([r[0] for r in rows])
    print(f"\n  replaced view high_earners: {names}")
    assert "Carol" in names
    assert "Dave" in names


def test_drop_view():
    db = make_db()
    db.create_view("high_earners", "SELECT name, salary FROM emp WHERE salary > 70000")
    db.drop_view("high_earners")
    assert "high_earners" not in db.views
    print("\n  view dropped correctly")


def test_view_persistence():
    db = make_db()
    db.create_view("high_earners", "SELECT name, salary FROM emp WHERE salary > 70000")
    db2 = Database()
    print(f"\n  views after reload: {list(db2.views.keys())}")
    assert "high_earners" in db2.views


def test_explain_full_scan():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM emp")
    result = db.get_table("emp").explain(sc, c, o, g, j, am)
    print(f"\n  EXPLAIN full scan:\n{result}")
    assert "Full table scan" in result


def test_explain_index_scan():
    db = make_db()
    db.get_table("emp").create_index("salary")
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM emp WHERE salary = 80000")
    result = db.get_table("emp").explain(sc, c, o, g, j, am)
    print(f"\n  EXPLAIN index scan:\n{result}")
    assert "Index scan" in result


def test_explain_group_by():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT dept_id, COUNT(*) FROM emp GROUP BY dept_id")
    result = db.get_table("emp").explain(sc, c, o, g, j, am)
    print(f"\n  EXPLAIN GROUP BY:\n{result}")
    assert "GROUP BY" in result


def test_explain_join():
    db = make_db()
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM emp INNER JOIN dept ON emp.dept_id = dept.id")
    result = db.get_table("emp").explain(sc, c, o, g, j, am)
    print(f"\n  EXPLAIN JOIN:\n{result}")
    assert "JOIN" in result
    assert "nested loop" in result
