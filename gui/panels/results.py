from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QLabel, QHeaderView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class ResultsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel("Results")
        self.label.setStyleSheet("font-weight: bold; font-size: 13px;")
        header_layout.addWidget(self.label)

        self.message = QLabel("")
        self.message.setStyleSheet("font-size: 11px; color: #6b7280;")
        header_layout.addWidget(self.message)

        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setFont(QFont("Courier New", 10))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)

        # Each column stretches equally — no empty white space
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #e5e7eb;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #f3f4f6;
                padding: 6px 10px;
                border: none;
                border-right: 1px solid #d1d5db;
                border-bottom: 2px solid #d1d5db;
                font-weight: bold;
                font-size: 12px;
                color: #111827;
            }
            QTableWidget::item {
                padding: 4px 10px;
                border-bottom: 1px solid #f3f4f6;
            }
            QTableWidget::item:selected {
                background-color: #dbeafe;
                color: #1e3a5f;
            }
            QTableWidget::item:alternate {
                background-color: #f9fafb;
            }
        """)
        layout.addWidget(self.table)

    def display(self, columns: list, rows: list, message: str):
        """
        Populate the results table with column headers and row data.
        Columns stretch evenly across the full panel width.
        For non-SELECT operations, clears the table and shows the status message.
        """
        self.message.setText(message)

        if message.startswith("Error"):
            self.message.setStyleSheet("font-size: 11px; color: #dc2626;")
        else:
            self.message.setStyleSheet("font-size: 11px; color: #6b7280;")

        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

        if not columns or not rows:
            return

        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)

        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                self.table.setItem(row_idx, col_idx, item)