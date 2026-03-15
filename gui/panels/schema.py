from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget,
    QTreeWidgetItem, QLabel
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"


class SchemaPanel(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setFixedWidth(240)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)

        label = QLabel("Tables")
        label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; "
            f"text-transform: uppercase; letter-spacing: 0.5px;"
        )
        layout.addWidget(label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(QFont("JetBrains Mono, Cascadia Code, Courier New", 11))
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
            QTreeWidget::item:hover {{
                background-color: #1f1f1f;
            }}
            QTreeWidget::item:selected {{
                background-color: #00e59915;
                color: {ACCENT};
            }}
            QTreeWidget::branch {{
                background-color: {BACKGROUND};
            }}
        """)
        layout.addWidget(self.tree)

    def refresh(self):
        """
        Rebuild the tree from the current database state.
        Called after any DDL operation that changes the schema.

        Tree structure:
            table_name
                id  int  [PK]
                name  string
        """
        self.tree.clear()

        for table_name, table in sorted(self.db.tables.items()):
            # Table root node -accent colored
            table_item = QTreeWidgetItem([f"  {table_name}"])
            table_item.setFont(0, QFont("Segoe UI", 11, QFont.Weight.Bold))
            table_item.setForeground(0, QColor(TEXT_PRIMARY))

            for col_name, col_type in table.columns:
                # Build constraint tag string
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
                col_item.setForeground(0, QColor(TEXT_MUTED))
                col_item.setFont(
                    0, QFont("JetBrains Mono, Cascadia Code, Courier New", 10)
                )

                # Highlight PK column name in accent color
                if col_name == table.primary_key:
                    col_item.setForeground(0, QColor(ACCENT))

                table_item.addChild(col_item)

            self.tree.addTopLevelItem(table_item)
            table_item.setExpanded(True)