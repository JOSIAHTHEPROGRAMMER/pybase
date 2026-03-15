from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter
)
from PyQt6.QtCore import Qt

from core.database import Database
from gui.panels.editor import EditorPanel
from gui.panels.results import ResultsPanel
from gui.panels.schema import SchemaPanel
from gui.widgets.status_bar import TransactionStatusBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyBase")
        self.setMinimumSize(1100, 700)

        # Single shared Database instance - all panels talk to this
        self.db = Database()

        self._build_ui()

    def _build_ui(self):
        # Central widget holds the entire layout
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 4)
        root_layout.setSpacing(4)

        # Main horizontal splitter: schema browser | editor + results
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - schema browser
        self.schema_panel = SchemaPanel(self.db)
        main_splitter.addWidget(self.schema_panel)

        # Right side - editor on top, results on bottom
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Editor panel - takes db and a callback to refresh schema after DDL
        self.editor_panel = EditorPanel(
            self.db,
            on_result=self._on_query_result,
            on_schema_change=self._refresh_schema,
            on_transaction_change=self._update_transaction_status
        )
        right_splitter.addWidget(self.editor_panel)

        # Results panel
        self.results_panel = ResultsPanel()
        right_splitter.addWidget(self.results_panel)

        # Give editor ~35% height, results ~65%
        right_splitter.setSizes([220, 450])

        right_layout.addWidget(right_splitter)
        main_splitter.addWidget(right_widget)

        # Give schema browser ~20% width, editor+results ~80%
        main_splitter.setSizes([220, 880])

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

    def _refresh_schema(self):
        """
        Called after DDL operations (CREATE TABLE, DROP TABLE, CREATE INDEX)
        so the schema browser reflects the current state.
        """
        self.schema_panel.refresh()

    def _update_transaction_status(self):
        """
        Called after BEGIN, COMMIT, ROLLBACK so the status bar updates.
        """
        self.status_bar.update_status(self.db.in_transaction())