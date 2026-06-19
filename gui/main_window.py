from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter, QToolButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize

from core.database import Database
from gui.panels.editor import EditorPanel
from gui.panels.results import ResultsPanel
from gui.panels.schema import SchemaPanel
from gui.widgets.status_bar import TransactionStatusBar

BACKGROUND = "#0f0f0f"
BORDER     = "#2e2e2e"

# Width thresholds for responsive behaviour
COMPACT_BREAKPOINT = 900   # collapse schema panel entirely
NARROW_BREAKPOINT  = 1100  # shrink schema panel to min width


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create resize timer FIRST
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._on_resize_settled)

        self.setWindowTitle("PyBase")
        self.setMinimumSize(600, 400)

        self._apply_global_style()

        # Splitter ratio memory (0–1 fractions of total width)
        self._main_splitter_ratio: float = 0.20   # schema : rest
        self._right_splitter_ratio: float = 0.35  # editor : results

        self.db = Database()
        self._build_ui()

        # These can trigger resize events, so do them LAST
        self.resize(1400, 860)
        self.setWindowState(Qt.WindowState.WindowMaximized)

    #  Stylesheet                                                          #

    def _apply_global_style(self):
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
            QSplitter::handle:hover {{
                background-color: #444;
            }}
            QScrollBar:vertical {{
                background: #1a1a1a; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: #3a3a3a; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: #555; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar:horizontal {{
                background: #1a1a1a; height: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:horizontal {{
                background: #3a3a3a; border-radius: 4px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: #555; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

            /* Compact toggle button */
            QToolButton#schema_toggle {{
                background: transparent;
                border: 1px solid {BORDER};
                border-radius: 4px;
                color: #aaa;
                padding: 2px 6px;
                font-size: 11px;
            }}
            QToolButton#schema_toggle:hover {{
                background: #1e1e1e;
                color: #ededed;
            }}
        """)

    #  UI construction                                                     #

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 6)
        root_layout.setSpacing(4)

        # Main horizontal splitter: schema | editor+results
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(4)
        self.main_splitter.splitterMoved.connect(self._on_main_splitter_moved)

        #  Left: schema panel 
        self.schema_panel = SchemaPanel(self.db)
        self.schema_panel.setMinimumWidth(160)
        self.main_splitter.addWidget(self.schema_panel)

        #  Right: editor + results 
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Small toggle button so users can manually show/hide schema
        self._schema_visible = True
        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("schema_toggle")
        self._toggle_btn.setText("‹ Schema")
        self._toggle_btn.setToolTip("Toggle schema panel (Ctrl+\\)")
        self._toggle_btn.setFixedHeight(22)
        self._toggle_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._toggle_btn.clicked.connect(self._toggle_schema)
        right_layout.addWidget(
            self._toggle_btn, 0, Qt.AlignmentFlag.AlignLeft
        )

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setHandleWidth(4)
        self.right_splitter.splitterMoved.connect(self._on_right_splitter_moved)

        self.editor_panel = EditorPanel(
            self.db,
            on_result=self._on_query_result,
            on_schema_change=self._refresh_schema,
            on_transaction_change=self._update_transaction_status,
        )
        self.right_splitter.addWidget(self.editor_panel)

        self.results_panel = ResultsPanel(self.db)
        self.right_splitter.addWidget(self.results_panel)

        self.right_splitter.setStretchFactor(0, 1)
        self.right_splitter.setStretchFactor(1, 2)

        right_layout.addWidget(self.right_splitter)
        self.main_splitter.addWidget(right_widget)

        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self.main_splitter)

        self.status_bar = TransactionStatusBar()
        root_layout.addWidget(self.status_bar)

        # Keyboard shortcut: Ctrl+\ toggles schema panel
        from PyQt6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+\\"), self).activated.connect(
            self._toggle_schema
        )

    #  Responsive resize logic                                             #

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "_resize_timer"):
            self._resize_timer.start()

    def _on_resize_settled(self):
        """Called once after the window stops being resized/snapped."""
        w = self.width()

        if w < COMPACT_BREAKPOINT:
            # Very narrow: hide schema panel entirely
            self._set_schema_visible(False)
            self._toggle_btn.setText("› Schema")

        elif w < NARROW_BREAKPOINT:
            # Narrow: keep schema visible but cap it at 180 px
            self._set_schema_visible(True)
            total = self.main_splitter.width()
            schema_w = min(180, int(total * self._main_splitter_ratio))
            self.main_splitter.setSizes([schema_w, total - schema_w])

        else:
            # Full width: restore saved ratio
            self._set_schema_visible(True)
            self._apply_main_ratio()

        # Restore right-splitter ratio regardless of width
        self._apply_right_ratio()

    def _apply_main_ratio(self):
        total = self.main_splitter.width()
        if total < 10:
            return
        schema_w = int(total * self._main_splitter_ratio)
        self.main_splitter.setSizes([schema_w, total - schema_w])

    def _apply_right_ratio(self):
        total = self.right_splitter.height()
        if total < 10:
            return
        editor_h = int(total * self._right_splitter_ratio)
        self.right_splitter.setSizes([editor_h, total - editor_h])

    #  Splitter ratio memory                                               #

    def _on_main_splitter_moved(self, pos: int, index: int):
        """Remember user-set schema ratio so resizes restore it."""
        sizes = self.main_splitter.sizes()
        total = sum(sizes)
        if total > 0 and sizes[0] > 0:
            self._main_splitter_ratio = sizes[0] / total

    def _on_right_splitter_moved(self, pos: int, index: int):
        sizes = self.right_splitter.sizes()
        total = sum(sizes)
        if total > 0:
            self._right_splitter_ratio = sizes[0] / total

    #  Schema panel toggle                                                 #

    def _toggle_schema(self):
        self._set_schema_visible(not self._schema_visible)

    def _set_schema_visible(self, visible: bool):
        if visible == self._schema_visible and self.schema_panel.isVisible() == visible:
            return
        self._schema_visible = visible
        if visible:
            self.schema_panel.show()
            self._toggle_btn.setText("‹ Schema")
            self._apply_main_ratio()
        else:
            self.schema_panel.hide()
            self._toggle_btn.setText("› Schema")

    #  Callbacks from child panels                                         #

    def _on_query_result(self, columns: list, rows: list, message: str):
        self.results_panel.display(columns, rows, message)
        self.schema_panel.refresh()

    def _refresh_schema(self):
        self.schema_panel.refresh()
        self.results_panel.refresh_er()

    def _update_transaction_status(self):
        self.status_bar.update_status(self.db.in_transaction())