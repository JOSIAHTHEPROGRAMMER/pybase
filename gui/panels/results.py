from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QLabel, QHeaderView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"
ROW_ALT      = "#161616"
ROW_SELECTED = "#00e59920"


class ResultsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout() if False else QVBoxLayout()
        self.label = QLabel("Results")
        self.label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-weight: 600; font-size: 13px;"
        )
        self.message = QLabel("")
        self.message.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.label)
        layout.addWidget(self.message)

        # Results table
        self.table = QTableWidget()
        self.table.setFont(QFont("JetBrains Mono, Cascadia Code, Courier New", 11))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)

        # Each column stretches equally across full width
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {PANEL};
                alternate-background-color: {ROW_ALT};
                color: {TEXT_PRIMARY};
                gridline-color: {BORDER};
                border: 1px solid {BORDER};
                border-radius: 6px;
                outline: none;
            }}
            QHeaderView::section {{
                background-color: #111111;
                color: {TEXT_MUTED};
                padding: 8px 12px;
                border: none;
                border-right: 1px solid {BORDER};
                border-bottom: 1px solid {BORDER};
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            QTableWidget::item {{
                padding: 6px 12px;
                color: {TEXT_PRIMARY};
                border-bottom: 1px solid {BORDER};
            }}
            QTableWidget::item:selected {{
                background-color: {ROW_SELECTED};
                color: {ACCENT};
            }}
            QTableWidget::item:alternate {{
                background-color: {ROW_ALT};
                color: {TEXT_PRIMARY};
            }}
        """)
        layout.addWidget(self.table)

    def display(self, columns: list, rows: list, message: str):
        """
        Populate the results table with column headers and row data.
        Columns stretch evenly across the full panel width.
        For non-SELECT operations, clears the table and shows the status message.
        """
        self.message.setText(message)

        # Color message based on outcome
        if message.startswith("Error"):
            self.message.setStyleSheet("font-size: 11px; color: #f87171;")
        elif message.startswith("Transaction"):
            self.message.setStyleSheet(f"font-size: 11px; color: {ACCENT};")
        elif message.startswith("Queued"):
            self.message.setStyleSheet("font-size: 11px; color: #fbbf24;")
        else:
            self.message.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")

        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

        if not columns or not rows:
            return

        # Set headers
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)

        # Populate rows
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setForeground(QColor(TEXT_PRIMARY))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                self.table.setItem(row_idx, col_idx, item)