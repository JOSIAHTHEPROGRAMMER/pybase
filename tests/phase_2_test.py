import os
import sys
import shutil
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Database
from cli import (
    parse_create_table, parse_insert, parse_select,
    parse_delete, parse_update, parse_compact_table
)
from storage.pager import Pager
from storage.page import PAGE_BODY_SIZE


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
        "CREATE TABLE docs (id int PRIMARY KEY, label string, body text, data blob, meta json, markup xml)",
    ]:
        tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(sql)
        t = db.create_table(tn, cols)
        if pk:
            t.set_primary_key(pk)
    return db


def insert_row(db, sql):
    tn, row = parse_insert(sql)
    db.get_table(tn).insert(row, db=db)


def sel(db, sql):
    t, sc, c, o, l, d, g, h, j, am = parse_select(sql)
    return db.get_table(t).select_advanced(sc, c, o, l, distinct=d)


# tombstone deletes

def test_tombstone_delete_hides_row():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'A', 'text a', x'aa', '{\"x\": 1}', '<r/>')")
    insert_row(db, "INSERT INTO docs VALUES (2, 'B', 'text b', x'bb', '{\"x\": 2}', '<r/>')")
    tn, conditions = parse_delete("DELETE FROM docs WHERE id = 1")
    db.get_table(tn).delete(conditions, db=db)
    rows = sel(db, "SELECT * FROM docs")
    ids = [r[0] for r in rows]
    print(f"\n  rows after tombstone delete: {ids}")
    assert 1 not in ids
    assert 2 in ids


def test_tombstone_survives_restart():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'A', 'text a', x'aa', '{\"x\": 1}', '<r/>')")
    insert_row(db, "INSERT INTO docs VALUES (2, 'B', 'text b', x'bb', '{\"x\": 2}', '<r/>')")
    tn, conditions = parse_delete("DELETE FROM docs WHERE id = 1")
    db.get_table(tn).delete(conditions, db=db)
    db2 = Database()
    rows = db2.get_table("docs").select_advanced(["*"], [], None, None)
    ids = [r[0] for r in rows]
    print(f"\n  rows after restart: {ids}")
    assert 1 not in ids
    assert 2 in ids


def test_compact_removes_tombstoned_rows():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'A', 'text a', x'aa', '{\"x\": 1}', '<r/>')")
    insert_row(db, "INSERT INTO docs VALUES (2, 'B', 'text b', x'bb', '{\"x\": 2}', '<r/>')")
    insert_row(db, "INSERT INTO docs VALUES (3, 'C', 'text c', x'cc', '{\"x\": 3}', '<r/>')")
    tn, conditions = parse_delete("DELETE FROM docs WHERE id = 2")
    db.get_table(tn).delete(conditions, db=db)
    db.get_table("docs").compact()
    rows = sel(db, "SELECT * FROM docs")
    ids = [r[0] for r in rows]
    print(f"\n  rows after compact: {ids}")
    assert 2 not in ids
    assert 1 in ids and 3 in ids

    # verify compact survives restart with correct rows
    db2  = Database()
    rows2 = db2.get_table("docs").select_advanced(["*"], [], None, None)
    ids2  = [r[0] for r in rows2]
    print(f"\n  rows after compact and restart: {ids2}")
    assert 2 not in ids2
    assert 1 in ids2 and 3 in ids2


# text and blob

def test_text_roundtrip():
    db = make_db()
    long_text = "A" * 1000
    insert_row(db, f"INSERT INTO docs VALUES (1, 'T', '{long_text}', x'aa', '{{\"x\": 1}}', '<r/>')")
    rows = sel(db, "SELECT * FROM docs WHERE id = 1")
    print(f"\n  text length roundtrip: {len(rows[0][2])}")
    assert rows[0][2] == long_text


def test_blob_roundtrip():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'B', 'text', x'deadbeef', '{\"x\": 1}', '<r/>')")
    rows = sel(db, "SELECT * FROM docs WHERE id = 1")
    print(f"\n  blob roundtrip: {rows[0][3]}")
    assert rows[0][3] == bytes.fromhex("deadbeef")


def test_blob_null():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'N', 'text', NULL, '{\"x\": 1}', '<r/>')")
    rows = sel(db, "SELECT * FROM docs WHERE id = 1")
    print(f"\n  null blob: {rows[0][3]}")
    assert rows[0][3] is None


# json validation

def test_json_valid_accepted():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'J', 'text', x'aa', '{\"key\": \"value\"}', '<r/>')")
    rows = sel(db, "SELECT * FROM docs WHERE id = 1")
    print(f"\n  valid json stored: {rows[0][4]}")
    assert rows[0][4] == '{"key": "value"}'


def test_json_invalid_rejected():
    db = make_db()
    with pytest.raises(ValueError, match="valid JSON"):
        insert_row(db, "INSERT INTO docs VALUES (1, 'J', 'text', x'aa', '{bad}', '<r/>')")
    print("\n  invalid JSON correctly rejected")


def test_json_update_validated():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'J', 'text', x'aa', '{\"x\": 1}', '<r/>')")
    t = db.get_table("docs")
    with pytest.raises(ValueError, match="valid JSON"):
        tn, assignments, conditions = parse_update("UPDATE docs SET meta = '{bad}' WHERE id = 1")
        t.update(assignments, conditions, db=db)
    print("\n  invalid JSON on update correctly rejected")


# xml validation

def test_xml_valid_accepted():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'X', 'text', x'aa', '{\"x\": 1}', '<root><item>1</item></root>')")
    rows = sel(db, "SELECT * FROM docs WHERE id = 1")
    print(f"\n  valid xml stored: {rows[0][5]}")
    assert rows[0][5] == "<root><item>1</item></root>"


def test_xml_invalid_rejected():
    db = make_db()
    with pytest.raises(ValueError, match="valid XML"):
        insert_row(db, "INSERT INTO docs VALUES (1, 'X', 'text', x'aa', '{\"x\": 1}', '<unclosed>')")
    print("\n  invalid XML correctly rejected")


def test_xml_update_validated():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'X', 'text', x'aa', '{\"x\": 1}', '<r/>')")
    t = db.get_table("docs")
    with pytest.raises(ValueError, match="valid XML"):
        tn, assignments, conditions = parse_update("UPDATE docs SET markup = '<bad' WHERE id = 1")
        t.update(assignments, conditions, db=db)
    print("\n  invalid XML on update correctly rejected")


# varchar and char

def test_varchar_roundtrip():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE vc (id int PRIMARY KEY, tag varchar(20))"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, "hello"], db=db)
    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  varchar roundtrip: {rows[0][1]}")
    assert rows[0][1] == "hello"


def test_varchar_max_length_enforced():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE vc (id int PRIMARY KEY, tag varchar(5))"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    with pytest.raises(ValueError):
        t.insert([1, "toolongvalue"], db=db)
    print("\n  varchar max length correctly enforced")


def test_char_roundtrip():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE ch (id int PRIMARY KEY, code char(3))"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, "ABC"], db=db)
    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  char roundtrip: {rows[0][1]}")
    assert rows[0][1] == "ABC"


# decimal and money

def test_decimal_roundtrip():
    from decimal import Decimal
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE prices (id int PRIMARY KEY, price decimal(10,2))"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, Decimal("19.99")], db=db)
    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  decimal roundtrip: {rows[0][1]}")
    assert rows[0][1] == Decimal("19.99")


def test_money_roundtrip():
    from decimal import Decimal
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE wallet (id int PRIMARY KEY, balance money)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, Decimal("1234.56")], db=db)
    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  money roundtrip: {rows[0][1]}")
    assert rows[0][1] == Decimal("1234.56")


# date and time types

def test_date_roundtrip():
    from datetime import date
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE events (id int PRIMARY KEY, day date)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, date(2025, 6, 15)], db=db)
    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  date roundtrip: {rows[0][1]}")
    assert rows[0][1] == date(2025, 6, 15)


def test_datetime_roundtrip():
    from datetime import datetime
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE log (id int PRIMARY KEY, ts datetime)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, datetime(2025, 6, 15, 10, 30, 0)], db=db)
    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  datetime roundtrip: {rows[0][1]}")
    assert rows[0][1] == datetime(2025, 6, 15, 10, 30, 0)


def test_time_roundtrip():
    from datetime import time
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE schedule (id int PRIMARY KEY, slot time)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, time(9, 0, 0)], db=db)
    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  time roundtrip: {rows[0][1]}")
    assert rows[0][1] == time(9, 0, 0)


# hash index

def test_hash_index_lookup():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'A', 'text', x'aa', '{\"x\": 1}', '<r/>')")
    insert_row(db, "INSERT INTO docs VALUES (2, 'B', 'text', x'bb', '{\"x\": 2}', '<r/>')")
    db.get_table("docs").create_hash_index("id")
    rows = db.get_table("docs").select_advanced(
        ["*"], [{"type": "simple", "column": "id", "op": "=", "value": 1}], None, None
    )
    print(f"\n  hash index lookup result: {rows}")
    assert len(rows) == 1
    assert rows[0][0] == 1


def test_hash_index_maintained_after_delete():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'A', 'text', x'aa', '{\"x\": 1}', '<r/>')")
    insert_row(db, "INSERT INTO docs VALUES (2, 'B', 'text', x'bb', '{\"x\": 2}', '<r/>')")
    db.get_table("docs").create_hash_index("id")
    tn, conditions = parse_delete("DELETE FROM docs WHERE id = 1")
    db.get_table(tn).delete(conditions, db=db)
    rows = db.get_table("docs").select_advanced(
        ["*"], [{"type": "simple", "column": "id", "op": "=", "value": 1}], None, None
    )
    print(f"\n  hash index after delete: {rows}")
    assert len(rows) == 0


# composite index

def test_composite_index_lookup():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE sales (id int PRIMARY KEY, region int, product int, amount int)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)
    t.insert([1, 1, 10, 500], db=db)
    t.insert([2, 1, 20, 300], db=db)
    t.insert([3, 2, 10, 700], db=db)
    t.create_composite_index(["region", "product"])
    rows = t.select_advanced(
        ["*"],
        [
            {"type": "simple", "column": "region",  "op": "=", "value": 1},
            {"type": "simple", "column": "product", "op": "=", "value": 10},
        ],
        None, None
    )
    print(f"\n  composite index lookup: {rows}")
    assert len(rows) == 1
    assert rows[0][0] == 1


# page based storage

def test_multiple_pages():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE big (id int PRIMARY KEY, payload text)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)

    # insert enough rows to span more than one 16KB page
    chunk = "X" * 500
    for i in range(1, 101):
        t.insert([i, chunk], db=db)

    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  rows across multiple pages: {len(rows)}")
    assert len(rows) == 100
    assert rows[0][0] == 1
    assert rows[99][0] == 100


def test_multiple_pages_survive_restart():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE big (id int PRIMARY KEY, payload text)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)

    chunk = "X" * 500
    for i in range(1, 51):
        t.insert([i, chunk], db=db)

    db2  = Database()
    rows = db2.get_table("big").select_advanced(["*"], [], None, None)
    ids  = [r[0] for r in rows]
    print(f"\n  rows after restart: {len(rows)}")
    assert len(rows) == 50
    assert 1 in ids and 50 in ids


# overflow rows

def test_overflow_row_roundtrip():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE overflow_test (id int PRIMARY KEY, body text)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)

    # value larger than one page body
    large = "Z" * (PAGE_BODY_SIZE + 500)
    t.insert([1, large], db=db)

    rows = t.select_advanced(["*"], [], None, None)
    print(f"\n  overflow row body length: {len(rows[0][1])}")
    assert rows[0][1] == large


def test_overflow_row_survives_restart():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE overflow_test (id int PRIMARY KEY, body text)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)

    large = "Z" * (PAGE_BODY_SIZE + 500)
    t.insert([1, large], db=db)

    db2  = Database()
    rows = db2.get_table("overflow_test").select_advanced(["*"], [], None, None)
    print(f"\n  overflow row after restart length: {len(rows[0][1])}")
    assert rows[0][1] == large


def test_overflow_row_delete():
    db = Database()
    tn, cols, uq, pk, fks, nn, dv, cc, ai = parse_create_table(
        "CREATE TABLE overflow_test (id int PRIMARY KEY, body text)"
    )
    t = db.create_table(tn, cols)
    t.set_primary_key(pk)

    large = "Z" * (PAGE_BODY_SIZE + 500)
    t.insert([1, large], db=db)
    t.insert([2, "small"], db=db)

    tn, conditions = parse_delete("DELETE FROM overflow_test WHERE id = 1")
    db.get_table(tn).delete(conditions, db=db)
    rows = t.select_advanced(["*"], [], None, None)
    ids  = [r[0] for r in rows]
    print(f"\n  after overflow delete: {ids}")
    assert 1 not in ids
    assert 2 in ids


# wal recovery

def test_wal_cleared_after_normal_operation():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'A', 'text', x'aa', '{\"x\": 1}', '<r/>')")
    wal_path = db.get_table("docs").pager.wal_path
    wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
    print(f"\n  WAL size after normal insert: {wal_size}")
    assert wal_size == 0


def test_wal_recovery_replays_page():
    db = make_db()
    insert_row(db, "INSERT INTO docs VALUES (1, 'A', 'text', x'aa', '{\"x\": 1}', '<r/>')")

    # simulate a crash by manually writing a WAL entry then reloading
    pager    = db.get_table("docs").pager
    page     = pager.read_page(0)
    page.write_tombstone(0)

    import zlib
    from storage.page import PAGE_SIZE
    data     = page.to_bytes()
    checksum = zlib.crc32(data) & 0xFFFFFFFF
    entry    = (
        (0).to_bytes(4, byteorder="big") +
        data +
        checksum.to_bytes(4, byteorder="big")
    )
    with open(pager.wal_path, "wb") as f:
        f.write(entry)

    # reload triggers recovery
    db2  = Database()
    rows = db2.get_table("docs").select_advanced(["*"], [], None, None)
    print(f"\n  rows after WAL recovery replay: {rows}")
    assert len(rows) == 0