import json
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QComboBox, QPushButton, QLabel
)
from PyQt6.QtGui import QFont

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"

HISTORY_FILE = os.path.join("data", "history.json")
MAX_HISTORY  = 100


class QueryHistoryBar(QWidget):
    """
    Dropdown bar that sits above the SQL editor.
    Stores the last MAX_HISTORY queries in data/history.json.
    Clicking a history entry loads it back into the editor via on_select callback.
    """

    def __init__(self, on_select):
        super().__init__()
        # Callback - called with the selected query string when user picks one
        self.on_select = on_select
        self.history = []
        self._load()
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel("History")
        label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; padding-left: 10 px;")
        layout.addWidget(label)

        self.dropdown = QComboBox()
        self.dropdown.setFont(QFont("Segoe UI", 11))
        self.dropdown.setPlaceholderText("Select a previous query...")
        self.dropdown.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.dropdown.setStyleSheet(f"""
            QComboBox {{
                background-color: {PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 12px;
            }}
            QComboBox:hover {{ border-color: #444; }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                selection-background-color: #00e59920;
                selection-color: {ACCENT};
                padding: 4px;
            }}
        """)

        self.dropdown.currentIndexChanged.connect(self._on_select)
        layout.addWidget(self.dropdown, stretch=1)

        # Clear history button
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(30)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 5px;
                font-size: 11px;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                color: #f87171;
                border-color: #f87171;
            }}
        """)
        clear_btn.clicked.connect(self._clear)
        layout.addWidget(clear_btn)

        self._refresh_dropdown()

    def _refresh_dropdown(self):
        """Rebuild the dropdown items from current history list."""
        self.dropdown.blockSignals(True)
        self.dropdown.clear()

        for entry in self.history:
            ts = entry.get("timestamp", "")
            query = entry.get("query", "")
            # Truncate long queries for display - full query stored in userData
            preview = query.replace("\n", " ").strip()
            if len(preview) > 60:
                preview = preview[:60] + "..."
            self.dropdown.addItem(f"[{ts}]  {preview}", userData=query)

        self.dropdown.blockSignals(False)

    def _on_select(self, index: int):
        """Load selected query back into the editor via callback."""
        if index < 0:
            return
        query = self.dropdown.itemData(index)
        if query:
            self.on_select(query)

    def add(self, query: str):
        """
        Add a new query to history.
        Skips consecutive duplicates.
        Caps at MAX_HISTORY entries, dropping oldest first.
        Persists to disk immediately after every addition.
        """
        query = query.strip()
        if not query:
            return

        # Skip if identical to most recent entry
        if self.history and self.history[0].get("query") == query:
            return

        entry = {
            "query": query,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }

        self.history.insert(0, entry)

        # Cap history length - drop oldest entries
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[:MAX_HISTORY]

        self._save()
        self._refresh_dropdown()

    def _clear(self):
        """Wipe all history from memory and disk."""
        self.history = []
        self._save()
        self._refresh_dropdown()

    def _load(self):
        """Load persisted history from disk on startup."""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f:
                    self.history = json.load(f)
        except Exception:
            # If file is corrupt or missing just start fresh
            self.history = []

    def _save(self):
        """Persist current history list to data/history.json."""
        try:
            os.makedirs("data", exist_ok=True)
            with open(HISTORY_FILE, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass
