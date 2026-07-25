import os
import sys
import pytest
from datetime import date, datetime, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from query.sql_parser import (
    parse_create_table, parse_insert, parse_select, parse_conditions,
    _parse_single_condition, _parse_value, parse_delete, parse_update,
    parse_alter_table, parse_truncate, parse_compact_table,
    parse_rename_table, parse_create_view, parse_drop_view, parse_explain,
    parse_create_index, parse_drop_table, parse_drop_database,
    _detect_set_operator, _split_column_defs, _split_values
)


# parse_create_table

def test_create_table_basic_columns():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE users (id int, name string)"
    )
    print(f"\n  table: {tn}, columns: {cols}")
    assert tn == "users"
    assert cols == [("id", "int"), ("name", "string")]


def test_create_table_primary_key():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE users (id int PRIMARY KEY, name string)"
    )
    print(f"\n  primary key: {pk}")
    assert pk == "id"


def test_create_table_unique():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE users (id int, email string UNIQUE)"
    )
    print(f"\n  unique columns: {uq}")
    assert uq == ["email"]


def test_create_table_not_null():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE users (id int, name string NOT NULL)"
    )
    print(f"\n  not null columns: {nn}")
    assert nn == ["name"]


def test_create_table_default_plain():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE users (id int, score int DEFAULT 0)"
    )
    print(f"\n  default values: {dv}")
    assert dv == {"score": 0}


def test_create_table_default_quoted_with_comma():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE messages (id int, note varchar(50) DEFAULT 'hello, world')"
    )
    print(f"\n  default with comma: {dv}")
    assert dv == {"note": "hello, world"}


def test_create_table_check_constraint():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE orders (id int, amount int CHECK (amount > 0))"
    )
    print(f"\n  check constraints: {cc}")
    assert cc == [{"column": "amount", "op": ">", "value": 0}]


def test_create_table_auto_increment():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE users (id int PRIMARY KEY AUTO_INCREMENT, name string)"
    )
    print(f"\n  auto increment column: {ai}")
    assert ai == "id"


def test_create_table_foreign_key_cascade():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE orders (id int, emp_id int REFERENCES emp(id) ON DELETE CASCADE ON UPDATE CASCADE)"
    )
    print(f"\n  foreign keys: {fks}")
    assert fks == [{
        "column": "emp_id", "ref_table": "emp", "ref_column": "id",
        "on_delete": "CASCADE", "on_update": "CASCADE"
    }]


def test_create_table_enum_type_preserved():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE orders (id int, status enum(pending,shipped,delivered))"
    )
    print(f"\n  columns with enum: {cols}")
    assert cols == [("id", "int"), ("status", "enum(pending,shipped,delivered)")]


def test_create_table_uuid_type_preserved():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE sessions (id int, token uuid)"
    )
    print(f"\n  columns with uuid: {cols}")
    assert cols == [("id", "int"), ("token", "uuid")]


def test_create_table_smallint_tinyint_preserved():
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE readings (temp_c tinyint, sensor_count smallint)"
    )
    print(f"\n  columns with smallint/tinyint: {cols}")
    assert cols == [("temp_c", "tinyint"), ("sensor_count", "smallint")]


# parse_insert

def test_insert_basic_values():
    tn, row = parse_insert("INSERT INTO users VALUES (1, 'Alice')")
    print(f"\n  table: {tn}, row: {row}")
    assert tn == "users"
    assert row == [1, "Alice"]


def test_insert_quoted_string_with_comma():
    tn, row = parse_insert("INSERT INTO messages VALUES (1, 'hello, world')")
    print(f"\n  row with comma: {row}")
    assert row == [1, "hello, world"]


def test_insert_null_value():
    tn, row = parse_insert("INSERT INTO users VALUES (NULL, 'Bob')")
    print(f"\n  row with NULL: {row}")
    assert row == [None, "Bob"]


def test_insert_hex_blob_literal():
    tn, row = parse_insert("INSERT INTO docs VALUES (1, x'deadbeef')")
    print(f"\n  row with blob: {row}")
    assert row == [1, bytes.fromhex("deadbeef")]


def test_insert_negative_number():
    tn, row = parse_insert("INSERT INTO readings VALUES (NULL, -40)")
    print(f"\n  row with negative number: {row}")
    assert row == [None, -40]


# parse_select

def test_select_basic():
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM users")
    print(f"\n  table: {t}, columns: {sc}")
    assert t == "users"
    assert sc == ["*"]


def test_select_where():
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM users WHERE id = 1")
    print(f"\n  conditions: {c}")
    assert c == [{"type": "simple", "column": "id", "op": "=", "value": 1}]


def test_select_order_by_single():
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM users ORDER BY name DESC")
    print(f"\n  order by: {o}")
    assert o == [("name", "DESC")]


def test_select_order_by_multi():
    t, sc, c, o, l, d, g, h, j, am = parse_select(
        "SELECT * FROM emp ORDER BY dept_id ASC, salary DESC"
    )
    print(f"\n  multi order by: {o}")
    assert o == [("dept_id", "ASC"), ("salary", "DESC")]


def test_select_limit():
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM users LIMIT 5")
    print(f"\n  limit: {l}")
    assert l == 5


def test_select_group_by_having():
    t, sc, c, o, l, d, g, h, j, am = parse_select(
        "SELECT dept_id, COUNT(*) FROM emp GROUP BY dept_id HAVING COUNT(*) > 1"
    )
    print(f"\n  group by: {g}, having: {h}")
    assert g == ["dept_id"]
    assert h == [{"type": "simple", "column": "count(*)", "op": ">", "value": 1}]


def test_select_distinct():
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT DISTINCT dept_id FROM emp")
    print(f"\n  distinct: {d}")
    assert d is True


def test_select_column_alias():
    t, sc, c, o, l, d, g, h, j, am = parse_select(
        "SELECT name AS employee, salary AS pay FROM emp"
    )
    print(f"\n  alias map: {am}")
    assert am == {"name": "employee", "salary": "pay"}
    assert sc == ["name", "salary"]


def test_select_table_alias_stripped():
    t, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM users AS u")
    print(f"\n  table name with alias stripped: {t}")
    assert t == "users"


def test_select_detects_join():
    t, sc, c, o, l, d, g, h, j, am = parse_select(
        "SELECT * FROM emp INNER JOIN dept ON emp.dept_id = dept.id"
    )
    print(f"\n  join info: {j}")
    assert j is not None
    assert j["join_type"] == "INNER"
    assert j["left_table"] == "emp"
    assert j["right_table"] == "dept"


# parse_conditions / _parse_single_condition

def test_condition_and():
    conditions = parse_conditions("id = 1 AND name = 'Bob'")
    print(f"\n  AND conditions: {conditions}")
    assert len(conditions) == 2


def test_condition_or():
    conditions = parse_conditions("id = 1 OR id = 2")
    print(f"\n  OR condition: {conditions}")
    assert len(conditions) == 1
    assert conditions[0]["type"] == "or"


def test_condition_between():
    cond = _parse_single_condition("salary BETWEEN 60000 AND 80000")
    print(f"\n  BETWEEN: {cond}")
    assert cond == {"type": "between", "column": "salary", "low": 60000, "high": 80000}


def test_condition_in():
    cond = _parse_single_condition("dept_id IN (1, 2, 3)")
    print(f"\n  IN: {cond}")
    assert cond == {"type": "in", "column": "dept_id", "values": [1, 2, 3]}


def test_condition_like():
    cond = _parse_single_condition("name LIKE 'A%'")
    print(f"\n  LIKE: {cond}")
    assert cond == {"type": "like", "column": "name", "pattern": "A%"}


def test_condition_is_null():
    cond = _parse_single_condition("dept_id IS NULL")
    print(f"\n  IS NULL: {cond}")
    assert cond == {"type": "is_null", "column": "dept_id", "negated": False}


def test_condition_is_not_null():
    cond = _parse_single_condition("dept_id IS NOT NULL")
    print(f"\n  IS NOT NULL: {cond}")
    assert cond == {"type": "is_null", "column": "dept_id", "negated": True}


def test_condition_arithmetic():
    cond = _parse_single_condition("salary + 10000 > 90000")
    print(f"\n  arithmetic condition: {cond}")
    assert cond["arithmetic"] == {"op": "+", "operand": 10000}


def test_condition_any():
    cond = _parse_single_condition("salary > ANY (SELECT salary FROM emp)")
    print(f"\n  ANY condition: {cond}")
    assert cond["type"] == "any_all"
    assert cond["qualifier"] == "ANY"


def test_condition_all():
    cond = _parse_single_condition("salary > ALL (SELECT salary FROM emp)")
    print(f"\n  ALL condition: {cond}")
    assert cond["type"] == "any_all"
    assert cond["qualifier"] == "ALL"


# _parse_value

def test_parse_value_int():
    print(f"\n  parsed int: {_parse_value('42')}")
    assert _parse_value("42") == 42


def test_parse_value_float():
    print(f"\n  parsed float: {_parse_value('3.14')}")
    assert _parse_value("3.14") == 3.14


def test_parse_value_quoted_string():
    print(f"\n  parsed quoted string: {_parse_value(chr(39) + 'hello' + chr(39))}")
    assert _parse_value("'hello'") == "hello"


def test_parse_value_null():
    print(f"\n  parsed NULL: {_parse_value('NULL')}")
    assert _parse_value("NULL") is None


def test_parse_value_true_false():
    print(f"\n  parsed TRUE/FALSE: {_parse_value('TRUE')}, {_parse_value('FALSE')}")
    assert _parse_value("TRUE") is True
    assert _parse_value("FALSE") is False


def test_parse_value_date():
    print(f"\n  parsed date: {_parse_value(chr(39) + '2025-06-15' + chr(39))}")
    assert _parse_value("'2025-06-15'") == date(2025, 6, 15)


def test_parse_value_datetime():
    result = _parse_value("'2025-06-15 10:30:00'")
    print(f"\n  parsed datetime: {result}")
    assert result == datetime(2025, 6, 15, 10, 30, 0)


def test_parse_value_time():
    print(f"\n  parsed time: {_parse_value(chr(39) + '09:00:00' + chr(39))}")
    assert _parse_value("'09:00:00'") == time(9, 0, 0)


def test_parse_value_hex_blob():
    print(f"\n  parsed hex blob: {_parse_value(chr(120) + chr(39) + 'aabb' + chr(39))}")
    assert _parse_value("x'aabb'") == bytes.fromhex("aabb")


# parse_delete / parse_update

def test_delete_basic():
    tn, conditions = parse_delete("DELETE FROM users WHERE id = 1")
    print(f"\n  delete table: {tn}, conditions: {conditions}")
    assert tn == "users"
    assert conditions == [{"type": "simple", "column": "id", "op": "=", "value": 1}]


def test_delete_requires_where():
    with pytest.raises(ValueError):
        parse_delete("DELETE FROM users")
    print("\n  DELETE without WHERE correctly rejected")


def test_update_basic():
    tn, assignments, conditions = parse_update("UPDATE users SET name = 'Bob' WHERE id = 1")
    print(f"\n  update table: {tn}, assignments: {assignments}")
    assert tn == "users"
    assert assignments == [("name", "Bob")]


def test_update_requires_where():
    with pytest.raises(ValueError):
        parse_update("UPDATE users SET name = 'Bob'")
    print("\n  UPDATE without WHERE correctly rejected")


# parse_alter_table

def test_alter_add_column():
    action, tn, col_a, col_b, extra = parse_alter_table(
        "ALTER TABLE users ADD COLUMN age int"
    )
    print(f"\n  alter add: {action}, {tn}, {col_a}, {col_b}")
    assert action == "add"
    assert col_a == "age"
    assert col_b == "int"


def test_alter_add_column_with_default():
    action, tn, col_a, col_b, extra = parse_alter_table(
        "ALTER TABLE users ADD COLUMN bonus int DEFAULT 0"
    )
    print(f"\n  alter add with default: {extra}")
    assert extra == 0


def test_alter_drop_column():
    action, tn, col_a, col_b, extra = parse_alter_table(
        "ALTER TABLE users DROP COLUMN age"
    )
    print(f"\n  alter drop: {action}, {col_a}")
    assert action == "drop"
    assert col_a == "age"


def test_alter_rename_column():
    action, tn, col_a, col_b, extra = parse_alter_table(
        "ALTER TABLE users RENAME COLUMN name TO full_name"
    )
    print(f"\n  alter rename: {action}, {col_a} -> {col_b}")
    assert action == "rename"
    assert col_a == "name"
    assert col_b == "full_name"


# truncate / compact / rename table

def test_parse_truncate():
    tn = parse_truncate("TRUNCATE TABLE orders")
    print(f"\n  truncate table: {tn}")
    assert tn == "orders"


def test_parse_compact_table():
    tn = parse_compact_table("COMPACT TABLE orders")
    print(f"\n  compact table: {tn}")
    assert tn == "orders"


def test_parse_rename_table():
    old_name, new_name = parse_rename_table("RENAME TABLE orders TO purchases")
    print(f"\n  rename: {old_name} -> {new_name}")
    assert old_name == "orders"
    assert new_name == "purchases"


# views

def test_parse_create_view():
    view_name, select_sql, replace = parse_create_view(
        "CREATE VIEW high_earners AS SELECT name FROM emp WHERE salary > 70000"
    )
    print(f"\n  view: {view_name}, replace: {replace}")
    assert view_name == "high_earners"
    assert replace is False


def test_parse_create_or_replace_view():
    view_name, select_sql, replace = parse_create_view(
        "CREATE OR REPLACE VIEW high_earners AS SELECT name FROM emp"
    )
    print(f"\n  or replace view: {view_name}, replace: {replace}")
    assert replace is True


def test_parse_drop_view():
    view_name = parse_drop_view("DROP VIEW high_earners")
    print(f"\n  drop view: {view_name}")
    assert view_name == "high_earners"


# explain

def test_parse_explain():
    inner = parse_explain("EXPLAIN SELECT * FROM users WHERE id = 1")
    print(f"\n  explain inner sql: {inner}")
    assert inner == "SELECT * FROM users WHERE id = 1"


# create index

def test_parse_create_index_single_column():
    tn, col = parse_create_index("CREATE INDEX ON users(name)")
    print(f"\n  index table: {tn}, column: {col}")
    assert tn == "users"
    assert col == "name"


def test_parse_create_index_composite():
    tn, cols = parse_create_index("CREATE INDEX ON sales(region, product)")
    print(f"\n  composite index columns: {cols}")
    assert cols == ["region", "product"]


# drop table / drop database

def test_parse_drop_table():
    tn = parse_drop_table("DROP TABLE users")
    print(f"\n  drop table: {tn}")
    assert tn == "users"


def test_parse_drop_database_valid():
    result = parse_drop_database("DROP DATABASE")
    print(f"\n  drop database valid: {result}")
    assert result is True


def test_parse_drop_database_invalid():
    with pytest.raises(ValueError):
        parse_drop_database("DROP DATABASE users")
    print("\n  malformed DROP DATABASE correctly rejected")


# set operator detection

def test_detect_union():
    result = _detect_set_operator("SELECT id FROM a UNION SELECT id FROM b")
    print(f"\n  detected: {result[0]}")
    assert result[0] == "UNION"


def test_detect_union_all():
    result = _detect_set_operator("SELECT id FROM a UNION ALL SELECT id FROM b")
    print(f"\n  detected: {result[0]}")
    assert result[0] == "UNION ALL"


def test_detect_intersect():
    result = _detect_set_operator("SELECT id FROM a INTERSECT SELECT id FROM b")
    print(f"\n  detected: {result[0]}")
    assert result[0] == "INTERSECT"


def test_detect_except():
    result = _detect_set_operator("SELECT id FROM a EXCEPT SELECT id FROM b")
    print(f"\n  detected: {result[0]}")
    assert result[0] == "EXCEPT"


def test_detect_no_set_operator():
    result = _detect_set_operator("SELECT id FROM a WHERE id = 1")
    print(f"\n  no set operator detected: {result}")
    assert result is None


# quote aware splitting

def test_split_column_defs_respects_quoted_comma():
    defs = _split_column_defs(
        "id int, note varchar(50) DEFAULT 'hello, world', priority int"
    )
    print(f"\n  split column defs: {defs}")
    assert len(defs) == 3
    assert defs[1] == "note varchar(50) DEFAULT 'hello, world'"


def test_split_column_defs_respects_parens():
    defs = _split_column_defs(
        "id int, status enum(pending,shipped,delivered)"
    )
    print(f"\n  split with enum parens: {defs}")
    assert len(defs) == 2
    assert defs[1] == "status enum(pending,shipped,delivered)"


def test_split_values_respects_quoted_comma():
    values = _split_values("1, 'hello, world', 3")
    print(f"\n  split values: {values}")
    assert values == ["1", "'hello, world'", "3"]
