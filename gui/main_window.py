from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter
)
from PyQt6.QtCore import Qt

from core.database import Database
from gui.panels.editor import EditorPanel
from gui.panels.results import ResultsPanel
from gui.panels.schema import SchemaPanel
from gui.widgets.status_bar import TransactionStatusBar

BACKGROUND = "#0f0f0f"
BORDER     = "#2e2e2e"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyBase")
        self.setMinimumSize(1200, 750)
        self._apply_global_style()

        # Single shared Database instance - all panels talk to this
        self.db = Database()
        self._build_ui()

    def _apply_global_style(self):
        """
        Apply a global dark stylesheet to the entire application window.
        Individual panels inherit this and override where needed.
        """
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {BACKGROUND};
                color: #ededed;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 13px;
            }}
            QSplitter::handle {{
                background-color: {BORDER};
            }}
            QScrollBar:vertical {{
                background: #1a1a1a;
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: #444;
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background: #1a1a1a;
                height: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal {{
                background: #444;
                border-radius: 4px;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 10, 10, 6)
        root_layout.setSpacing(6)

        # Main horizontal splitter: schema browser | editor + results
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(1)

        # Left panel - schema browser
        self.schema_panel = SchemaPanel(self.db)
        main_splitter.addWidget(self.schema_panel)

        # Right side - editor on top, results on bottom
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setHandleWidth(1)

        self.editor_panel = EditorPanel(
            self.db,
            on_result=self._on_query_result,
            on_schema_change=self._refresh_schema,
            on_transaction_change=self._update_transaction_status
        )
        right_splitter.addWidget(self.editor_panel)

        # ResultsPanel now takes db for ER diagram tab
        self.results_panel = ResultsPanel(self.db)
        right_splitter.addWidget(self.results_panel)

        right_splitter.setSizes([240, 460])
        right_layout.addWidget(right_splitter)
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([240, 960])

        root_layout.addWidget(main_splitter)

        # Transaction status bar at the bottom
        self.status_bar = TransactionStatusBar()
        root_layout.addWidget(self.status_bar)

    def _on_query_result(self, columns: list, rows: list, message: str):
        """
        Receives query results from EditorPanel and passes to ResultsPanel.
        columns: list of column name strings (empty for non-SELECT)
        rows:    list of row lists
        message: status message to display
        """
        self.results_panel.display(columns, rows, message)

        self.schema_panel.refresh()

             


    def _refresh_schema(self):
        """
        Called after DDL operations so schema browser and ER diagram
        both reflect the current state.
        """
        self.schema_panel.refresh()
        # Refresh ER diagram whenever schema changes
        self.results_panel.refresh_er()

    def _update_transaction_status(self):
        """
        Called after BEGIN, COMMIT, ROLLBACK so the status bar updates.
        """
        self.status_bar.update_status(self.db.in_transaction())