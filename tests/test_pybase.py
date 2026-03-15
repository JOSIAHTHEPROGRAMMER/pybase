import os
import shutil
import pytest
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Database

TEST_DATA_FOLDER = "test_data"


@pytest.fixture(autouse=True)
def clean_db():
    """
    Wipe test_data/ before and after every test.
    Before: handles leftover state from crashed previous runs.
    After:  normal cleanup.
    """
    if os.path.exists(TEST_DATA_FOLDER):
        shutil.rmtree(TEST_DATA_FOLDER)
    os.makedirs(TEST_DATA_FOLDER)

    yield

    if os.path.exists(TEST_DATA_FOLDER):
        shutil.rmtree(TEST_DATA_FOLDER)


def make_db():
    """Helper - fresh Database instance pointed at test folder."""
    return Database(folder=TEST_DATA_FOLDER)


# ─────────────────────────────────────────────
# CREATE TABLE
# ─────────────────────────────────────────────

class TestCreateTable:

    def test_create_table_success(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        assert table is not None
        assert "users" in db.tables

    def test_create_table_duplicate_raises(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        with pytest.raises(ValueError, match="already exists"):
            db.create_table("users", [("id", "int")])

    def test_create_table_unsupported_type_raises(self):
        db = make_db()
        with pytest.raises(ValueError, match="Unsupported column type"):
            db.create_table("users", [("id", "float")])

    def test_schema_file_created_on_disk(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        assert os.path.exists(os.path.join(TEST_DATA_FOLDER, "users.schema"))

    def test_db_file_created_on_disk(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        assert os.path.exists(os.path.join(TEST_DATA_FOLDER, "users.db"))


# ─────────────────────────────────────────────
# DROP TABLE
# ─────────────────────────────────────────────

class TestDropTable:

    def test_drop_table_removes_from_memory(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        db.drop_table("users")
        assert "users" not in db.tables

    def test_drop_table_removes_files_from_disk(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        db.drop_table("users")
        assert not os.path.exists(os.path.join(TEST_DATA_FOLDER, "users.db"))
        assert not os.path.exists(os.path.join(TEST_DATA_FOLDER, "users.schema"))

    def test_drop_nonexistent_table_raises(self):
        db = make_db()
        with pytest.raises(ValueError, match="does not exist"):
            db.drop_table("ghost")

    def test_drop_table_then_recreate(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        db.drop_table("users")
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        assert table is not None


# ─────────────────────────────────────────────
# INSERT
# ─────────────────────────────────────────────

class TestInsert:

    def test_insert_success(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        assert [1, "Alice"] in table.rows

    def test_insert_wrong_column_count_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        with pytest.raises(ValueError, match="Expected 2 values"):
            table.insert([1])

    def test_insert_wrong_type_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        with pytest.raises(TypeError, match="expects type 'int'"):
            table.insert(["not_an_int", "Alice"])

    def test_insert_duplicate_row_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        with pytest.raises(ValueError):
            table.insert([1, "Alice"])

    def test_insert_unique_violation_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.add_unique_constraint("id")
        table.insert([1, "Alice"])
        with pytest.raises(ValueError):
            # Different name, same id - hits UNIQUE not duplicate row check
            table.insert([1, "Bob"])

    def test_insert_primary_key_null_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.set_primary_key("id")
        # None fails type check before reaching PK null check - both are correct
        with pytest.raises((ValueError, TypeError)):
            table.insert([None, "Alice"])

    def test_insert_persists_to_disk(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])

        db2 = make_db()
        table2 = db2.get_table("users")
        assert [1, "Alice"] in table2.rows


# ─────────────────────────────────────────────
# SELECT
# ─────────────────────────────────────────────

class TestSelect:

    def test_select_all(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        rows = table.select_advanced(["*"], [])
        assert len(rows) == 2

    def test_select_with_equality_condition(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        rows = table.select_advanced(["*"], [("id", "=", 1)])
        assert rows == [[1, "Alice"]]

    def test_select_with_gt_condition(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        table.insert([3, "Charlie"])
        rows = table.select_advanced(["*"], [("id", ">", 1)])
        assert len(rows) == 2

    def test_select_with_gte_condition(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        rows = table.select_advanced(["*"], [("id", ">=", 1)])
        assert len(rows) == 2

    def test_select_with_neq_condition(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        rows = table.select_advanced(["*"], [("id", "!=", 1)])
        assert rows == [[2, "Bob"]]

    def test_select_column_projection(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        rows = table.select_advanced(["name"], [])
        assert rows == [["Alice"]]

    def test_select_invalid_column_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        with pytest.raises(ValueError, match="does not exist"):
            table.select_advanced(["ghost"], [])

    def test_select_order_by_asc(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([3, "Charlie"])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        rows = table.select_advanced(["*"], [], order_by=("id", "ASC"))
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_select_order_by_desc(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([3, "Charlie"])
        table.insert([2, "Bob"])
        rows = table.select_advanced(["*"], [], order_by=("id", "DESC"))
        assert [r[0] for r in rows] == [3, 2, 1]

    def test_select_limit(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        table.insert([3, "Charlie"])
        rows = table.select_advanced(["*"], [], limit=2)
        assert len(rows) == 2

    def test_select_order_by_and_limit(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([3, "Charlie"])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        rows = table.select_advanced(["*"], [], order_by=("id", "ASC"), limit=2)
        assert [r[0] for r in rows] == [1, 2]

    def test_select_no_results(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        rows = table.select_advanced(["*"], [("id", "=", 99)])
        assert rows == []


# ─────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────

class TestDelete:

    def test_delete_matching_row(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        count = table.delete([("id", "=", 1)])
        assert count == 1
        assert all(r[0] != 1 for r in table.rows)

    def test_delete_no_match_returns_zero(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        count = table.delete([("id", "=", 99)])
        assert count == 0

    def test_delete_without_conditions_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        with pytest.raises(ValueError, match="requires at least one WHERE condition"):
            table.delete([])

    def test_delete_persists_to_disk(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        table.delete([("id", "=", 1)])

        db2 = make_db()
        table2 = db2.get_table("users")
        assert all(r[0] != 1 for r in table2.rows)

    def test_delete_multiple_rows(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        table.insert([3, "Charlie"])
        count = table.delete([("id", ">", 1)])
        assert count == 2
        assert len(table.rows) == 1


# ─────────────────────────────────────────────
# UPDATE
# ─────────────────────────────────────────────

class TestUpdate:

    def test_update_success(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        count = table.update([("name", "Alice2")], [("id", "=", 1)])
        assert count == 1
        assert table.rows[0][1] == "Alice2"

    def test_update_no_match_returns_zero(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        count = table.update([("name", "Ghost")], [("id", "=", 99)])
        assert count == 0

    def test_update_without_conditions_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        with pytest.raises(ValueError, match="requires at least one WHERE condition"):
            table.update([("name", "X")], [])

    def test_update_unique_violation_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.add_unique_constraint("id")
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        with pytest.raises(ValueError, match="Duplicate value for UNIQUE"):
            table.update([("id", 1)], [("id", "=", 2)])

    def test_update_wrong_type_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        with pytest.raises(TypeError):
            table.update([("id", "not_an_int")], [("id", "=", 1)])

    def test_update_persists_to_disk(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.update([("name", "Alice2")], [("id", "=", 1)])

        db2 = make_db()
        table2 = db2.get_table("users")
        assert table2.rows[0][1] == "Alice2"


# ─────────────────────────────────────────────
# CONSTRAINTS
# ─────────────────────────────────────────────

class TestConstraints:

    def test_primary_key_enforces_unique(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.set_primary_key("id")
        table.insert([1, "Alice"])
        with pytest.raises(ValueError, match="Duplicate value for UNIQUE"):
            table.insert([1, "Bob"])

    def test_primary_key_persists_after_restart(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.set_primary_key("id")
        table.insert([1, "Alice"])

        db2 = make_db()
        table2 = db2.get_table("users")
        assert table2.primary_key == "id"
        with pytest.raises(ValueError, match="Duplicate value for UNIQUE"):
            table2.insert([1, "Bob"])

    def test_unique_constraint_persists_after_restart(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.add_unique_constraint("name")
        table.insert([1, "Alice"])

        db2 = make_db()
        table2 = db2.get_table("users")
        assert "name" in table2.unique_columns
        with pytest.raises(ValueError, match="Duplicate value for UNIQUE"):
            table2.insert([2, "Alice"])

    def test_only_one_primary_key_allowed(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.set_primary_key("id")
        with pytest.raises(ValueError, match="already has a primary key"):
            table.set_primary_key("name")


# ─────────────────────────────────────────────
# B-TREE INDEX
# ─────────────────────────────────────────────

class TestBTreeIndex:

    def test_create_index_success(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.create_index("id")
        assert table.index_manager.has_index("id")

    def test_index_lookup_returns_correct_row(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        table.create_index("id")
        rows = table.select_advanced(["*"], [("id", "=", 1)])
        assert rows == [[1, "Alice"]]

    def test_index_persists_after_restart(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.create_index("id")

        db2 = make_db()
        table2 = db2.get_table("users")
        assert table2.index_manager.has_index("id")

    def test_index_updated_after_insert(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.create_index("id")
        table.insert([1, "Alice"])
        rows = table.select_advanced(["*"], [("id", "=", 1)])
        assert rows == [[1, "Alice"]]

    def test_index_updated_after_delete(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        table.create_index("id")
        table.delete([("id", "=", 1)])
        rows = table.select_advanced(["*"], [("id", "=", 1)])
        assert rows == []

    def test_index_updated_after_update(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.create_index("id")
        table.update([("name", "Alice2")], [("id", "=", 1)])
        rows = table.select_advanced(["*"], [("id", "=", 1)])
        assert rows[0][1] == "Alice2"

    def test_duplicate_index_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.create_index("id")
        with pytest.raises(ValueError, match="already exists"):
            table.create_index("id")

    def test_index_on_nonexistent_column_raises(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        with pytest.raises(ValueError, match="does not exist"):
            table.create_index("ghost")


# ─────────────────────────────────────────────
# TRANSACTIONS
# ─────────────────────────────────────────────

class TestTransactions:

    def test_commit_applies_inserts(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        db.begin_transaction()
        db.current_transaction.add("insert", "users", row=[1, "Alice"])
        db.current_transaction.add("insert", "users", row=[2, "Bob"])
        db.commit_transaction()
        table = db.get_table("users")
        assert len(table.rows) == 2

    def test_rollback_discards_operations(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        db.begin_transaction()
        db.current_transaction.add("insert", "users", row=[1, "Alice"])
        db.rollback_transaction()
        table = db.get_table("users")
        assert len(table.rows) == 0

    def test_commit_applies_delete(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        db.begin_transaction()
        db.current_transaction.add("delete", "users", conditions=[("id", "=", 1)])
        db.commit_transaction()
        assert all(r[0] != 1 for r in table.rows)

    def test_commit_applies_update(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        db.begin_transaction()
        db.current_transaction.add(
            "update", "users",
            assignments=[("name", "Alice2")],
            conditions=[("id", "=", 1)]
        )
        db.commit_transaction()
        assert table.rows[0][1] == "Alice2"

    def test_nested_transaction_raises(self):
        db = make_db()
        db.begin_transaction()
        with pytest.raises(ValueError, match="already active"):
            db.begin_transaction()

    def test_commit_without_begin_raises(self):
        db = make_db()
        with pytest.raises(ValueError, match="No active transaction"):
            db.commit_transaction()

    def test_rollback_without_begin_raises(self):
        db = make_db()
        with pytest.raises(ValueError, match="No active transaction"):
            db.rollback_transaction()

    def test_in_transaction_true_after_begin(self):
        db = make_db()
        db.begin_transaction()
        assert db.in_transaction() is True

    def test_in_transaction_false_after_commit(self):
        db = make_db()
        db.begin_transaction()
        db.commit_transaction()
        assert db.in_transaction() is False

    def test_in_transaction_false_after_rollback(self):
        db = make_db()
        db.begin_transaction()
        db.rollback_transaction()
        assert db.in_transaction() is False

    def test_transaction_error_on_bad_insert(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.set_primary_key("id")
        table.insert([1, "Alice"])
        db.begin_transaction()
        db.current_transaction.add("insert", "users", row=[1, "Duplicate"])
        with pytest.raises(ValueError, match="Duplicate value for UNIQUE"):
            db.commit_transaction()


# ─────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────

class TestPersistence:

    def test_table_reloads_on_restart(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])

        db2 = make_db()
        assert "users" in db2.tables

    def test_rows_persist_across_restart(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])

        db2 = make_db()
        table2 = db2.get_table("users")
        assert len(table2.rows) == 2
        assert [1, "Alice"] in table2.rows
        assert [2, "Bob"] in table2.rows

    def test_delete_persists_across_restart(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.insert([2, "Bob"])
        table.delete([("id", "=", 1)])

        db2 = make_db()
        table2 = db2.get_table("users")
        assert all(r[0] != 1 for r in table2.rows)

    def test_update_persists_across_restart(self):
        db = make_db()
        table = db.create_table("users", [("id", "int"), ("name", "string")])
        table.insert([1, "Alice"])
        table.update([("name", "Alice2")], [("id", "=", 1)])

        db2 = make_db()
        table2 = db2.get_table("users")
        assert table2.rows[0][1] == "Alice2"

    def test_dropped_table_does_not_reload(self):
        db = make_db()
        db.create_table("users", [("id", "int"), ("name", "string")])
        db.drop_table("users")

        db2 = make_db()
        assert "users" not in db2.tables
