import os
import sys
import shutil
import pytest
from unittest.mock import Mock

# pytest-qt needs a display. On headless machines and CI runners this must
# be set before any Qt widget is created, so it is set here before imports.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPlainTextEdit

from core.database import Database
from gui.panels.schema import SchemaPanel
from gui.panels.editor import EditorPanel
from gui.panels.results import ResultsPanel
from gui.main_window import MainWindow


DATA_DIR = "data"


@pytest.fixture(autouse=True)
def clean_data():
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR)
    yield


def make_db_with_table():
    db = Database()
    db.create_table("users", [("id", "int"), ("name", "string")])
    db.tables["users"].set_primary_key("id")
    db.tables["users"].insert([1, "Alice"], db=db)
    db.tables["users"].insert([2, "Bob"], db=db)
    return db


# SchemaPanel

def test_schema_panel_refresh_populates_tree(qtbot):
    db = make_db_with_table()
    panel = SchemaPanel(db)
    qtbot.addWidget(panel)

    print(f"\n  top level items: {panel.tree.topLevelItemCount()}")
    assert panel.tree.topLevelItemCount() == 1

    table_item = panel.tree.topLevelItem(0)
    print(f"  table item text: {table_item.text(0)}")
    assert "users" in table_item.text(0)
    assert table_item.childCount() == 2


def test_schema_panel_table_click_triggers_callback(qtbot):
    db = make_db_with_table()
    on_table_selected = Mock()
    panel = SchemaPanel(db, on_table_selected=on_table_selected)
    qtbot.addWidget(panel)

    table_item = panel.tree.topLevelItem(0)
    panel._on_item_clicked(table_item, 0)

    print(f"\n  on_table_selected called with: {on_table_selected.call_args}")
    on_table_selected.assert_called_once_with("users")


def test_schema_panel_column_double_click_triggers_stats(qtbot):
    db = make_db_with_table()
    panel = SchemaPanel(db)
    qtbot.addWidget(panel)

    table_item = panel.tree.topLevelItem(0)
    column_item = table_item.child(0)
    data = column_item.data(0, Qt.ItemDataRole.UserRole)
    print(f"\n  column item data: {data}")

    panel._show_column_stats(data["table"], data["column"])
    print(f"  stats dialog created: {panel._stats_dialog is not None}")
    assert panel._stats_dialog is not None


def test_schema_panel_rename_table(qtbot):
    db = make_db_with_table()
    on_schema_change = Mock()
    panel = SchemaPanel(db, on_schema_change=on_schema_change)
    qtbot.addWidget(panel)

    db.rename_table("users", "customers")
    panel._notify_change()

    print(f"\n  tables after rename: {list(db.tables.keys())}")
    assert "customers" in db.tables
    on_schema_change.assert_called_once()


def test_schema_panel_truncate_table(qtbot, monkeypatch):
    db = make_db_with_table()
    panel = SchemaPanel(db)
    qtbot.addWidget(panel)

    # _truncate_table opens a real confirm dialog via QMessageBox.exec(),
    # which blocks waiting for a click. Patch it to simulate "Yes".
    monkeypatch.setattr(panel, "_confirm", lambda *args, **kwargs: True)

    panel._truncate_table("users")

    print(f"\n  rows after truncate: {len(db.tables['users'].rows)}")
    assert len(db.tables["users"].rows) == 0


def test_schema_panel_create_index(qtbot):
    db = make_db_with_table()
    panel = SchemaPanel(db)
    qtbot.addWidget(panel)

    panel._create_index("users", "name")

    print(f"\n  has index on name: {db.tables['users'].index_manager.has_index('name')}")
    assert db.tables["users"].index_manager.has_index("name")


def test_schema_panel_create_hash_index(qtbot):
    db = make_db_with_table()
    panel = SchemaPanel(db)
    qtbot.addWidget(panel)

    panel._create_hash_index("users", "name")

    print(f"\n  has hash index on name: {db.tables['users'].index_manager.has_hash_index('name')}")
    assert db.tables["users"].index_manager.has_hash_index("name")


def test_schema_panel_drop_table_error_shows_dialog_not_crash(qtbot, monkeypatch):
    db = make_db_with_table()
    panel = SchemaPanel(db)
    qtbot.addWidget(panel)

    # _drop_table opens a real confirm dialog before attempting the drop,
    # and _show_error opens a real error dialog if the drop fails.
    # Both call QMessageBox.exec(), which blocks waiting for a click.
    monkeypatch.setattr(panel, "_confirm", lambda *args, **kwargs: True)
    monkeypatch.setattr(panel, "_show_error", lambda *args, **kwargs: None)

    # dropping a table that does not exist should be caught and shown,
    # not raise out of the panel
    try:
        panel._drop_table("does_not_exist")
        errored = False
    except Exception:
        errored = True

    print(f"\n  error escaped panel: {errored}")
    assert errored is False


# EditorPanel

def test_editor_panel_set_query_replaces_text(qtbot):
    db = make_db_with_table()
    panel = EditorPanel(db, Mock(), Mock(), Mock(), Mock())
    qtbot.addWidget(panel)

    panel.set_query("SELECT * FROM users;")

    print(f"\n  editor text: {panel.editor.toPlainText()}")
    assert panel.editor.toPlainText() == "SELECT * FROM users;"


def test_editor_panel_create_table_calls_schema_change(qtbot):
    db = Database()
    on_result = Mock()
    on_schema_change = Mock()
    panel = EditorPanel(db, on_result, on_schema_change, Mock(), Mock())
    qtbot.addWidget(panel)

    panel.editor.setPlainText("CREATE TABLE items (id int PRIMARY KEY, label string);")
    panel._run_query()

    print(f"\n  tables after create: {list(db.tables.keys())}")
    assert "items" in db.tables
    on_schema_change.assert_called_once()
    on_result.assert_called_once()


def test_editor_panel_select_calls_on_result_with_rows(qtbot):
    db = make_db_with_table()
    on_result = Mock()
    panel = EditorPanel(db, on_result, Mock(), Mock(), Mock())
    qtbot.addWidget(panel)

    panel.editor.setPlainText("SELECT * FROM users;")
    panel._run_query()

    args = on_result.call_args[0]
    print(f"\n  on_result args: {args}")
    assert len(args[1]) == 2  # two rows inserted in make_db_with_table


def test_editor_panel_invalid_sql_returns_false_and_reports_error(qtbot):
    db = make_db_with_table()
    on_result = Mock()
    panel = EditorPanel(db, on_result, Mock(), Mock(), Mock())
    qtbot.addWidget(panel)

    result = panel._execute_single("SELECT * FROM does_not_exist")

    print(f"\n  execute result: {result}, on_result args: {on_result.call_args}")
    assert result is False
    assert "Error" in on_result.call_args[0][2]


def test_editor_panel_explain_calls_on_explain(qtbot):
    db = make_db_with_table()
    on_explain = Mock()
    panel = EditorPanel(db, Mock(), Mock(), Mock(), on_explain)
    qtbot.addWidget(panel)

    panel.editor.setPlainText("EXPLAIN SELECT * FROM users;")
    panel._run_query()

    print(f"\n  on_explain called: {on_explain.called}")
    on_explain.assert_called_once()


# ResultsPanel

def test_results_panel_display_populates_table(qtbot):
    db = make_db_with_table()
    panel = ResultsPanel(db)
    qtbot.addWidget(panel)

    panel.display(["id", "name"], [[1, "Alice"], [2, "Bob"]], "2 row(s) returned.")

    print(f"\n  row count: {panel.table.rowCount()}, col count: {panel.table.columnCount()}")
    assert panel.table.rowCount() == 2
    assert panel.table.columnCount() == 2


def test_results_panel_export_button_disabled_when_empty(qtbot):
    db = make_db_with_table()
    panel = ResultsPanel(db)
    qtbot.addWidget(panel)

    print(f"\n  export button enabled before any results: {panel.export_btn.isEnabled()}")
    assert panel.export_btn.isEnabled() is False


def test_results_panel_export_button_enabled_after_results(qtbot):
    db = make_db_with_table()
    panel = ResultsPanel(db)
    qtbot.addWidget(panel)

    panel.display(["id", "name"], [[1, "Alice"]], "1 row(s) returned.")

    print(f"\n  export button enabled after results: {panel.export_btn.isEnabled()}")
    assert panel.export_btn.isEnabled() is True


def test_results_panel_export_writes_csv(qtbot, tmp_path, monkeypatch):
    db = make_db_with_table()
    panel = ResultsPanel(db)
    qtbot.addWidget(panel)

    panel.display(["id", "name"], [[1, "Alice"], [2, "Bob"]], "2 row(s) returned.")

    out_path = str(tmp_path / "export.csv")
    monkeypatch.setattr(
        "gui.panels.results.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (out_path, "CSV Files (*.csv)")
    )

    panel._export_csv()

    with open(out_path, "r", encoding="utf-8") as f:
        content = f.read()

    print(f"\n  exported csv content:\n{content}")
    assert "id,name" in content
    assert "1,Alice" in content
    assert "2,Bob" in content


# MainWindow end-to-end

def test_main_window_create_and_query_updates_panels(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.editor_panel.editor.setPlainText(
        "CREATE TABLE items (id int PRIMARY KEY, label string);"
    )
    window.editor_panel._run_query()

    print(f"\n  tables after create via editor: {list(window.db.tables.keys())}")
    assert "items" in window.db.tables

    table_names = [
        window.schema_panel.tree.topLevelItem(i).text(0)
        for i in range(window.schema_panel.tree.topLevelItemCount())
    ]
    print(f"  schema tree entries: {table_names}")
    assert any("items" in name for name in table_names)


def test_main_window_table_click_fills_editor_and_runs(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.db.create_table("users", [("id", "int"), ("name", "string")])
    window.db.tables["users"].set_primary_key("id")
    window.db.tables["users"].insert([1, "Alice"], db=window.db)
    window.schema_panel.refresh()

    table_item = window.schema_panel.tree.topLevelItem(0)
    window.schema_panel._on_item_clicked(table_item, 0)

    print(f"\n  editor text after table click: {window.editor_panel.editor.toPlainText()}")
    assert window.editor_panel.editor.toPlainText() == "SELECT * FROM users;"

    window.editor_panel._run_query()
    print(f"  results table row count: {window.results_panel.table.rowCount()}")
    assert window.results_panel.table.rowCount() == 1


def test_main_window_explain_opens_dialog(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.db.create_table("users", [("id", "int"), ("name", "string")])
    window.db.tables["users"].set_primary_key("id")

    window.editor_panel.editor.setPlainText("EXPLAIN SELECT * FROM users;")
    window.editor_panel._run_query()

    print(f"\n  explain dialog present: {hasattr(window, '_explain_dialog')}")
    assert hasattr(window, "_explain_dialog")
    plan_text = window._explain_dialog.findChild(QPlainTextEdit).toPlainText()
    print(f"  explain plan text: {plan_text}")
    assert "Full table scan" in plan_text