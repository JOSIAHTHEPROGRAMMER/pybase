import os
import sys
import shutil
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Database
from query.sql_parser import parse_create_table, parse_select
from query.dispatch import execute_statement


DATA_DIR = "data"


@pytest.fixture(autouse=True)
def clean_data():
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR)
    yield


def sel(db, sql):
    t, sc, c, o, l, d, g, h, j, am = parse_select(sql)
    return db.get_table(t).select_advanced(sc, c, o, l, distinct=d)


def run(db, sql, confirm=None):
    """
    Run a single statement through the shared dispatch layer.
    Returns (success, col_names, rows, message) from the last on_result call.
    """
    captured = {}

    def on_result(col_names, rows, message):
        captured["col_names"] = col_names
        captured["rows"] = rows
        captured["message"] = message

    success = execute_statement(sql, db, on_result=on_result, confirm=confirm or (lambda *a: True))
    return success, captured.get("col_names", []), captured.get("rows", []), captured.get("message", "")


# ENUM type

def test_enum_valid_insert():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE orders (id int PRIMARY KEY, status enum(pending,shipped,delivered))"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, "pending"], db=db)
    rows = sel(db, "SELECT * FROM orders")
    print(f"\n  enum row: {rows}")
    assert rows[0][1] == "pending"


def test_enum_invalid_value_rejected():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE orders (id int PRIMARY KEY, status enum(pending,shipped,delivered))"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    with pytest.raises(ValueError):
        t.insert([1, "cancelled"], db=db)
    print("\n  invalid enum value correctly rejected")


def test_enum_null_allowed():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE orders (id int PRIMARY KEY, status enum(pending,shipped,delivered))"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, None], db=db)
    rows = sel(db, "SELECT * FROM orders")
    print(f"\n  enum NULL row: {rows}")
    assert rows[0][1] is None


def test_enum_persists_across_restart():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE orders (id int PRIMARY KEY, status enum(pending,shipped,delivered))"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, "shipped"], db=db)

    db2 = Database()
    rows = db2.get_table("orders").select_advanced(["*"], [], None, None)
    print(f"\n  enum after restart: {rows}")
    assert rows[0][1] == "shipped"


# UUID type

def test_uuid_valid_insert():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE sessions (id int PRIMARY KEY, token uuid)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, "550e8400-e29b-41d4-a716-446655440000"], db=db)
    rows = sel(db, "SELECT * FROM sessions")
    print(f"\n  uuid row: {rows}")
    assert rows[0][1] == "550e8400-e29b-41d4-a716-446655440000"


def test_uuid_invalid_value_rejected():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE sessions (id int PRIMARY KEY, token uuid)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    with pytest.raises(ValueError):
        t.insert([1, "not-a-uuid"], db=db)
    print("\n  invalid uuid correctly rejected")


def test_uuid_persists_across_restart():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE sessions (id int PRIMARY KEY, token uuid)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, "123e4567-e89b-12d3-a456-426614174000"], db=db)

    db2 = Database()
    rows = db2.get_table("sessions").select_advanced(["*"], [], None, None)
    print(f"\n  uuid after restart: {rows}")
    assert rows[0][1] == "123e4567-e89b-12d3-a456-426614174000"


# smallint and tinyint

def test_tinyint_range_enforced():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE readings (id int PRIMARY KEY, temp_c tinyint)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, 127], db=db)
    with pytest.raises(ValueError):
        t.insert([2, 128], db=db)
    print("\n  tinyint range correctly enforced")


def test_smallint_range_enforced():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE readings (id int PRIMARY KEY, sensor_count smallint)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, 32767], db=db)
    with pytest.raises(ValueError):
        t.insert([2, 40000], db=db)
    print("\n  smallint range correctly enforced")


def test_smallint_tinyint_persist_across_restart():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE readings (id int PRIMARY KEY, temp_c tinyint, sensor_count smallint)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, -40, -500], db=db)

    db2 = Database()
    rows = db2.get_table("readings").select_advanced(["*"], [], None, None)
    print(f"\n  smallint/tinyint after restart: {rows}")
    assert rows[0][1] == -40
    assert rows[0][2] == -500


# auto increment does not burn a value on a failed insert

def test_auto_increment_not_consumed_on_failed_insert():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE readings (id int PRIMARY KEY AUTO_INCREMENT, temp_c tinyint)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.set_auto_increment(pk)

    t.insert([None, 20], db=db)
    with pytest.raises(ValueError):
        t.insert([None, 200], db=db)  # out of range, should fail before consuming id
    t.insert([None, 21], db=db)

    rows = sel(db, "SELECT * FROM readings")
    ids = [r[0] for r in rows]
    print(f"\n  ids after one failed insert in between: {ids}")
    assert ids == [1, 2]


# rows and row_offsets stay in sync after a failed insert

def test_rows_and_offsets_stay_in_sync_after_failed_insert():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE readings (id int PRIMARY KEY AUTO_INCREMENT, temp_c tinyint)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.set_auto_increment(pk)

    t.insert([None, 20], db=db)
    with pytest.raises(ValueError):
        t.insert([None, 200], db=db)

    assert len(t.rows) == len(t.row_offsets)

    updated = t.update([("temp_c", 99)], [{"type": "simple", "column": "id", "op": "=", "value": 1}], db=db)
    print(f"\n  rows/offsets len: {len(t.rows)}/{len(t.row_offsets)}, updated count: {updated}")
    assert updated == 1


# quote aware DEFAULT with comma

def test_default_value_with_comma_survives_create_table():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE messages (id int PRIMARY KEY, note varchar(50) DEFAULT 'hello, world')"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    for col, val in dv.items():
        t.set_default_value(col, val)
    t.insert([1, None], db=db)
    rows = sel(db, "SELECT * FROM messages")
    print(f"\n  default with comma applied: {rows}")
    assert rows[0][1] == "hello, world"


# CREATE TYPE composite types

def test_create_type_basic_and_nested():
    db = Database()
    db.create_type("address", [("street", "varchar(50)"), ("city", "varchar(30)"), ("zip", "varchar(10)")])
    db.create_type("contact", [("email", "varchar(50)"), ("home", "address")])
    print(f"\n  custom types: {list(db.custom_types.keys())}")
    assert "address" in db.custom_types
    assert "contact" in db.custom_types


def test_create_type_rejects_unsupported_field_type():
    db = Database()
    with pytest.raises(ValueError):
        db.create_type("bad_type", [("amount", "decimal(10,2)")])
    print("\n  unsupported composite field type correctly rejected")


def test_composite_type_insert_valid_value():
    db = Database()
    db.create_type("address", [("street", "varchar(50)"), ("city", "varchar(30)"), ("zip", "varchar(10)")])
    t = db.create_table("people", [("id", "int"), ("home_address", "json")])
    t.set_primary_key("id")
    t.register_custom_type_column("home_address", "address")

    t.insert([1, '{"street": "Main St", "city": "Springfield", "zip": "12345"}'], db=db)
    rows = sel(db, "SELECT * FROM people")
    print(f"\n  composite value stored: {rows}")
    assert "Main St" in rows[0][1]


def test_composite_type_insert_missing_field_rejected():
    db = Database()
    db.create_type("address", [("street", "varchar(50)"), ("city", "varchar(30)"), ("zip", "varchar(10)")])
    t = db.create_table("people", [("id", "int"), ("home_address", "json")])
    t.set_primary_key("id")
    t.register_custom_type_column("home_address", "address")

    with pytest.raises(ValueError, match="Missing field"):
        t.insert([1, '{"street": "Main St", "city": "Springfield"}'], db=db)
    print("\n  missing composite field correctly rejected")


def test_composite_type_insert_extra_field_rejected():
    db = Database()
    db.create_type("address", [("street", "varchar(50)"), ("city", "varchar(30)"), ("zip", "varchar(10)")])
    t = db.create_table("people", [("id", "int"), ("home_address", "json")])
    t.set_primary_key("id")
    t.register_custom_type_column("home_address", "address")

    with pytest.raises(ValueError, match="Unexpected fields"):
        t.insert([1, '{"street": "Main St", "city": "Springfield", "zip": "12345", "country": "USA"}'], db=db)
    print("\n  unexpected composite field correctly rejected")


def test_composite_type_insert_wrong_field_type_rejected():
    db = Database()
    db.create_type("address", [("street", "varchar(50)"), ("city", "varchar(30)"), ("zip", "varchar(10)")])
    t = db.create_table("people", [("id", "int"), ("home_address", "json")])
    t.set_primary_key("id")
    t.register_custom_type_column("home_address", "address")

    with pytest.raises(ValueError):
        t.insert([1, '{"street": 123, "city": "Springfield", "zip": "12345"}'], db=db)
    print("\n  wrong composite field type correctly rejected")


def test_nested_composite_type_validation():
    db = Database()
    db.create_type("address", [("street", "varchar(50)"), ("city", "varchar(30)"), ("zip", "varchar(10)")])
    db.create_type("contact", [("email", "varchar(50)"), ("home", "address")])
    t = db.create_table("people", [("id", "int"), ("info", "json")])
    t.set_primary_key("id")
    t.register_custom_type_column("info", "contact")

    valid = '{"email": "a@b.com", "home": {"street": "Oak Ave", "city": "Shelbyville", "zip": "54321"}}'
    t.insert([1, valid], db=db)
    rows = sel(db, "SELECT * FROM people")
    print(f"\n  nested composite stored: {rows}")
    assert "Oak Ave" in rows[0][1]

    invalid = '{"email": "a@b.com", "home": {"street": "Oak Ave", "city": "Shelbyville"}}'
    with pytest.raises(ValueError, match="Missing field"):
        t.insert([2, invalid], db=db)
    print("  nested composite missing field correctly rejected")


def test_drop_type_blocked_while_column_in_use():
    db = Database()
    db.create_type("address", [("street", "varchar(50)")])
    t = db.create_table("people", [("id", "int"), ("home_address", "json")])
    t.set_primary_key("id")
    t.register_custom_type_column("home_address", "address")

    with pytest.raises(ValueError, match="in use"):
        db.drop_type("address")
    print("\n  DROP TYPE correctly blocked while column in use")


def test_drop_type_blocked_while_referenced_by_another_type():
    db = Database()
    db.create_type("address", [("street", "varchar(50)")])
    db.create_type("contact", [("home", "address")])

    with pytest.raises(ValueError, match="referenced"):
        db.drop_type("address")
    print("\n  DROP TYPE correctly blocked while referenced by another type")


def test_drop_type_succeeds_once_unused():
    db = Database()
    db.create_type("address", [("street", "varchar(50)")])
    db.drop_type("address")
    print(f"\n  types after drop: {list(db.custom_types.keys())}")
    assert "address" not in db.custom_types


# stored procedures

def test_create_and_call_self_referential_arithmetic_procedure():
    db = Database()
    t = db.create_table("emp2", [("id", "int"), ("name", "varchar(50)"), ("salary", "int")])
    t.set_primary_key("id")
    t.set_auto_increment("id")
    t.insert([None, "Alice", 60000], db=db)

    success, cn, rows, msg = run(
        db,
        "CREATE PROCEDURE give_raise(emp_id int, amount int) AS BEGIN "
        "UPDATE emp2 SET salary = salary + amount WHERE id = emp_id; END"
    )
    print(f"\n  create procedure: {success}, {msg}")
    assert success is True

    success, cn, rows, msg = run(db, "CALL give_raise(1, 5000)")
    print(f"  call procedure: {success}, {msg}")
    assert success is True

    result = sel(db, "SELECT * FROM emp2 WHERE id = 1")
    print(f"  salary after call: {result}")
    assert result[0][2] == 65000


def test_call_literal_arithmetic_procedure():
    db = Database()
    t = db.create_table("emp2", [("id", "int"), ("name", "varchar(50)"), ("salary", "int")])
    t.set_primary_key("id")
    t.set_auto_increment("id")

    run(db, "CREATE PROCEDURE onboard(new_name varchar, start_salary int) AS BEGIN "
            "INSERT INTO emp2 VALUES (NULL, new_name, start_salary); "
            "UPDATE emp2 SET salary = start_salary + 1000 WHERE name = new_name; END")

    success, cn, rows, msg = run(db, "CALL onboard('Carol', 50000)")
    print(f"\n  call multi-statement procedure: {success}, {msg}")
    assert success is True

    result = sel(db, "SELECT * FROM emp2 WHERE name = 'Carol'")
    print(f"  Carol row: {result}")
    assert result[0][2] == 51000


def test_call_wrong_argument_count_rejected():
    db = Database()
    run(db, "CREATE PROCEDURE noop_proc(a int, b int) AS BEGIN "
            "SELECT * FROM does_not_matter; END")
    success, cn, rows, msg = run(db, "CALL noop_proc(1)")
    print(f"\n  wrong arg count message: {msg}")
    assert success is False
    assert "expects 2 argument" in msg


def test_create_procedure_allows_deferred_table_reference():
    db = Database()
    success, cn, rows, msg = run(
        db,
        "CREATE PROCEDURE archive_high(threshold int) AS BEGIN "
        "UPDATE nonexistent_table SET x = threshold WHERE id = 1; END"
    )
    print(f"\n  create procedure with unresolved table: {success}, {msg}")
    assert success is True
    assert db.has_procedure("archive_high")


def test_call_surfaces_failure_from_deferred_procedure():
    db = Database()
    run(db, "CREATE PROCEDURE archive_high(threshold int) AS BEGIN "
            "UPDATE nonexistent_table SET x = threshold WHERE id = 1; END")
    success, cn, rows, msg = run(db, "CALL archive_high(100)")
    print(f"\n  call failure message: {msg}")
    assert success is False
    assert "Statement failed inside procedure" in msg


def test_drop_procedure():
    db = Database()
    run(db, "CREATE PROCEDURE noop_proc(a int) AS BEGIN SELECT * FROM x; END")
    success, cn, rows, msg = run(db, "DROP PROCEDURE noop_proc")
    print(f"\n  drop procedure: {success}, {msg}")
    assert success is True
    assert not db.has_procedure("noop_proc")


def test_procedure_persists_across_restart():
    db = Database()
    run(db, "CREATE PROCEDURE noop_proc(a int) AS BEGIN SELECT * FROM x; END")

    db2 = Database()
    print(f"\n  procedures after restart: {list(db2.procedures.keys())}")
    assert db2.has_procedure("noop_proc")


# drop database wipes views, custom types, and procedures

def test_drop_database_wipes_views_types_and_procedures():
    db = Database()
    db.create_table("t1", [("id", "int")])
    db.create_view("v1", "SELECT * FROM t1")
    db.create_type("addr", [("street", "varchar(50)")])
    run(db, "CREATE PROCEDURE noop_proc(a int) AS BEGIN SELECT * FROM t1; END")

    db.drop_database()

    print(f"\n  after drop_database: views={db.views}, types={db.custom_types}, procs={db.procedures}")
    assert db.views == {}
    assert db.custom_types == {}
    assert db.procedures == {}

    db2 = Database()
    print(f"  after restart: views={db2.views}, types={db2.custom_types}, procs={db2.procedures}")
    assert db2.views == {}
    assert db2.custom_types == {}
    assert db2.procedures == {}


# EXPLAIN hash index detection

def test_explain_reports_hash_index_scan():
    db = Database()
    t = db.create_table("staff2", [("id", "int"), ("name", "varchar(50)")])
    t.set_primary_key("id")
    t.insert([1, "alice"], db=db)
    t.create_hash_index("name")

    tn, sc, c, o, l, d, g, h, j, am = parse_select("SELECT * FROM staff2 WHERE name = 'alice'")
    result = t.explain(sc, c, o, g, j, am)
    print(f"\n  explain with hash index:\n{result}")
    assert "Hash index scan" in result