from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget,
    QTreeWidgetItem, QLabel
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class SchemaPanel(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setFixedWidth(220)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel("Schema Browser")
        label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(QFont("Segoe UI", 10))
        self.tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #d1d5db;
                border-radius: 4px;
            }
            QTreeWidget::item { padding: 3px 4px; }
            QTreeWidget::item:selected {
                background-color: #dbeafe;
                color: #1e3a5f;
            }
        """)
        layout.addWidget(self.tree)

    def refresh(self):
        """
        Rebuild the tree from the current database state.
        Called after any DDL operation that changes the schema.

        Tree structure:
              table_name
                  id (int) [PK]
                · name (string) [UNIQUE]
                · email (string)
        """
        self.tree.clear()

        for table_name, table in sorted(self.db.tables.items()):
            # Table root node
            table_item = QTreeWidgetItem([f"  {table_name}"])
            table_item.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))

            for col_name, col_type in table.columns:
                # Build label with constraint annotations
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
                col_item.setForeground(0, Qt.GlobalColor.darkGray)
                table_item.addChild(col_item)

            self.tree.addTopLevelItem(table_item)
            table_item.setExpanded(True)