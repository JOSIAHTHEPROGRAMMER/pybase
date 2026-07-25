from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget,
    QTreeWidgetItem, QLabel, QMenu, QMessageBox, QInputDialog
)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from gui.widgets.font import get_mono_font
from gui.widgets.column_stats_dialog import ColumnStatsDialog

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"


class SchemaPanel(QWidget):
    def __init__(self, db, on_schema_change=None, on_table_selected=None):
        super().__init__()
        self.db = db
        self.on_schema_change = on_schema_change
        self.on_table_selected = on_table_selected
        self.setMinimumWidth(200)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)

        label = QLabel("Tables")
        label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(get_mono_font(11))

        self.tree.setIndentation(16)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {BACKGROUND};
                border: none;
                color: {TEXT_PRIMARY};
                outline: none;
              
            }}
            QTreeWidget::item {{
                padding: 3px 4px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{ background-color: #1f1f1f; }}
            QTreeWidget::item:selected {{
                background-color: #00e59915;
                color: {ACCENT};
            }}
            QTreeWidget::branch {{ background-color: {BACKGROUND}; }}
        """)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

    def refresh(self):
        """
        Rebuild the tree from the current database state.
        Shows table name, row count, and all columns with constraint tags.
        Called after any DDL operation.

        Tree structure:
            users  (3 rows)
                id    int   [PK] [IDX]
                name  string
        """
        self.tree.clear()

        for table_name, table in sorted(self.db.tables.items()):
            row_count = len(table.rows)
            row_label = f"1 row" if row_count == 1 else f"{row_count} rows"

            # Table root - name + row count
            table_item = QTreeWidgetItem([f"  {table_name}  ({row_label})"])
            table_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "table", "table": table_name})
            table_item.setFont(0, QFont("Segoe UI", 11, QFont.Weight.Bold))
            table_item.setForeground(0, QColor(TEXT_PRIMARY))

            for col_name, col_type in table.columns:
                tags = []
                if col_name == table.primary_key:
                    tags.append("PK")
                elif col_name in table.unique_columns:
                    tags.append("UNIQUE")
                if table.index_manager.has_index(col_name):
                    tags.append("IDX")

                tag_str = f"  [{', '.join(tags)}]" if tags else ""
                label = f"    {col_name}  {col_type}{tag_str}"

                col_item = QTreeWidgetItem([label])
                col_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "column", "table": table_name, "column": col_name})
                col_item.setForeground(0, QColor(TEXT_MUTED))
                col_item.setFont(0, get_mono_font(10))


                if col_name == table.primary_key:
                    col_item.setForeground(0, QColor(ACCENT))

                table_item.addChild(col_item)

            self.tree.addTopLevelItem(table_item)
            table_item.setExpanded(True)
    


    def _on_item_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "table" and self.on_table_selected:
            self.on_table_selected(data["table"])

    def _on_item_double_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "column":
            self._show_column_stats(data["table"], data["column"])

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "table":
            self._show_table_menu(data["table"], pos)
        elif data["type"] == "column":
            self._show_column_menu(data["table"], data["column"], pos)

    def _menu_stylesheet(self) -> str:
        return f"""
            QMenu {{
                background-color: {PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: #00e59920;
                color: {ACCENT};
            }}
            QMenu::separator {{
                height: 1px;
                background: {BORDER};
                margin: 4px 6px;
            }}
        """

    def _show_table_menu(self, table_name, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())

        refresh_action  = menu.addAction("Refresh")
        menu.addSeparator()
        rename_action   = menu.addAction("Rename Table...")
        truncate_action = menu.addAction("Truncate Table...")
        compact_action  = menu.addAction("Compact Table")
        menu.addSeparator()
        drop_action     = menu.addAction("Drop Table...")

        action = menu.exec(self.tree.viewport().mapToGlobal(pos))

        if action == refresh_action:
            self.refresh()
        elif action == rename_action:
            self._rename_table(table_name)
        elif action == truncate_action:
            self._truncate_table(table_name)
        elif action == compact_action:
            self._compact_table(table_name)
        elif action == drop_action:
            self._drop_table(table_name)

    def _show_column_menu(self, table_name, column_name, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())

        stats_action       = menu.addAction("Column Stats")
        menu.addSeparator()
        index_action       = menu.addAction("Create Index")
        hash_index_action  = menu.addAction("Create Hash Index")

        action = menu.exec(self.tree.viewport().mapToGlobal(pos))

        if action == stats_action:
            self._show_column_stats(table_name, column_name)
        elif action == index_action:
            self._create_index(table_name, column_name)
        elif action == hash_index_action:
            self._create_hash_index(table_name, column_name)

    def _confirm(self, title, text, informative) -> bool:
        confirm = QMessageBox(self)
        confirm.setWindowTitle(title)
        confirm.setText(text)
        confirm.setInformativeText(informative)
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return confirm.exec() == QMessageBox.StandardButton.Yes
    
    def _show_error(self, message: str):
        error_box = QMessageBox(self)
        error_box.setWindowTitle("Error")
        error_box.setText(message)
        error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        error_box.exec()

    def _rename_table(self, table_name):
        new_name, ok = QInputDialog.getText(
            self, "Rename Table", f"New name for '{table_name}':"
        )
        if not ok or not new_name.strip():
            return
        try:
            self.db.rename_table(table_name, new_name.strip())
            self._notify_change()
        except Exception as e:
            self._show_error(str(e))

    def _truncate_table(self, table_name):
        if not self._confirm(
            "Confirm Truncate Table",
            f"Truncate table '{table_name}'?",
            "This will permanently delete all rows in this table. This cannot be undone."
        ):
            return
        try:
            self.db.get_table(table_name).truncate()
            self._notify_change()
        except Exception as e:
            self._show_error(str(e))

    def _compact_table(self, table_name):
        try:
            self.db.get_table(table_name).compact()
            self._notify_change()
        except Exception as e:
            self._show_error(str(e))

    def _drop_table(self, table_name):
        if not self._confirm(
            "Confirm Drop Table",
            f"Drop table '{table_name}'?",
            "This will permanently delete the table and all its data. This cannot be undone."
        ):
            return
        try:
            self.db.drop_table(table_name)
            self._notify_change()
        except Exception as e:
            self._show_error(str(e))

    def _create_index(self, table_name, column_name):
        try:
            self.db.get_table(table_name).create_index(column_name)
            self._notify_change()
        except Exception as e:
            self._show_error(str(e))

    def _show_column_stats(self, table_name, column_name):
        try:
            stats = self.db.get_table(table_name).column_stats(column_name)
        except Exception as e:
            self._show_error(str(e))
            return

        dialog = ColumnStatsDialog(table_name, stats, parent=self)
        dialog.show()
        self._stats_dialog = dialog  # keep a reference so it isn't garbage collected

    def _create_hash_index(self, table_name, column_name):
        try:
            self.db.get_table(table_name).create_hash_index(column_name)
            self._notify_change()
        except Exception as e:
            self._show_error(str(e))

    def _notify_change(self):
        self.refresh()
        if self.on_schema_change:
            self.on_schema_change()