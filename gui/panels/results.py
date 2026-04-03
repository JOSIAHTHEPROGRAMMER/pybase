from PyQt6.QtWidgets import (
    QPlainTextEdit, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
     QHeaderView, QTabWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from gui.widgets.font import get_mono_font

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"
ROW_ALT      = "#161616"
ROW_SELECTED = "#00e59920"


class ResultsPanel(QWidget):
    def __init__(self, db):
        super().__init__()
        # db reference needed by ER diagram tab
        self.db = db
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Status message above tabs
        self.message = QPlainTextEdit()
        self.message.setReadOnly(True)
        self.message.setFixedHeight(36)
        self.message.setFont(get_mono_font(11))
        self.message.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: transparent;
                color: {TEXT_MUTED};
                border: none;
                font-size: 11px;
                padding: 2px 0px;
                selection-background-color: #00e59933;
                selection-color: {TEXT_PRIMARY};
            }}
        """)
        layout.addWidget(self.message)


        
        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {BORDER};
                border-radius: 6px;
                background-color: {PANEL};
            }}
            QTabBar::tab {{
                background-color: {BACKGROUND};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                padding: 6px 18px;
                font-size: 12px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {PANEL};
                color: {ACCENT};
                border-bottom: 2px solid {ACCENT};
            }}
            QTabBar::tab:hover {{
                color: {TEXT_PRIMARY};
            }}
        """)

        # Tab 1 - Results table
        self.table_tab = self._build_table_tab()
        self.tabs.addTab(self.table_tab, "Table")

        # Tab 2 - Bar chart (imported lazily to avoid circular imports)
        from gui.panels.chart import ChartPanel
        self.chart_panel = ChartPanel()
        self.tabs.addTab(self.chart_panel, "Chart")

        # Tab 3 - ER Diagram
        from gui.panels.er_diagram import ERDiagramPanel
        self.er_panel = ERDiagramPanel(self.db)
        self.tabs.addTab(self.er_panel, "ER Diagram")

        layout.addWidget(self.tabs)

    def _build_table_tab(self) -> QWidget:
        """Build the results table widget for Tab 1."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setFont(QFont("JetBrains Mono, Cascadia Code, Courier New", 11))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)

        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setStyleSheet(f"""
            QHeaderView::section {{
                background-color: #111111;
                color: {TEXT_MUTED};
                border: none;
                border-right: 1px solid {BORDER};
                border-bottom: 1px solid {BORDER};
                padding: 0 6px;
                font-size: 10px;
            }}
        """)

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {PANEL};
                alternate-background-color: {ROW_ALT};
                color: {TEXT_PRIMARY};
                gridline-color: {BORDER};
                border: none;
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
        return widget

    def display(self, columns: list, rows: list, message: str):
        """
        Populate the table tab and pass data to chart tab.
        ER diagram is always live and doesn't need data passed to it.
        """
        self.message.setPlainText(message)

        if message.startswith("Error"):
            self.message.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: transparent;
                    color: #f87171;
                    border: none;
                    font-size: 11px;
                    padding: 2px 0px;
                    selection-background-color: #f8717133;
                    selection-color: #f87171;
                }}
            """)
            
        elif message.startswith("Transaction"):
            self.message.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: transparent;
                    color: {ACCENT};
                    border: none;
                    font-size: 11px;
                    padding: 2px 0px;
                    selection-background-color: #00e59933;
                    selection-color: {ACCENT};
                }}
            """)

        elif message.startswith("Queued"):
            self.message.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: transparent;
                    color: #fbbf24;
                    border: none;
                    font-size: 11px;
                    padding: 2px 0px;
                    selection-background-color: #fbbf2433;
                    selection-color: #fbbf24;
                }}
            """)

        else:
            self.message.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: transparent;
                    color: {TEXT_MUTED};
                    border: none;
                    font-size: 11px;
                    padding: 2px 0px;
                    selection-background-color: #00e59933;
                    selection-color: {TEXT_PRIMARY};
                }}
            """)

        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

        self.chart_panel.update_chart(columns, rows)

        if not columns or not rows:
            return

        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            self.table.setVerticalHeaderItem(
                row_idx, QTableWidgetItem(str(row_idx + 1))
            )
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setForeground(QColor(TEXT_PRIMARY))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                self.table.setItem(row_idx, col_idx, item)


    def refresh_er(self):
        """
        Called after DDL operations so the ER diagram redraws.
        """
        self.er_panel.refresh()