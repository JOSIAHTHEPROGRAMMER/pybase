from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QLabel
from PyQt6.QtCore import Qt

from gui.widgets.font import get_mono_font

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"


class ExplainDialog(QDialog):
    """
    Non-modal window showing a query plan from EXPLAIN.
    Stays open alongside the main window so the plan can be
    compared against the editor while working.
    """

    def __init__(self, plan_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Query Plan")
        self.setMinimumSize(480, 260)
        self.resize(520, 320)
        self.setWindowModality(Qt.WindowModality.NonModal)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BACKGROUND};
                color: {TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel("EXPLAIN output")
        label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(label)

        text = QPlainTextEdit()
        text.setPlainText(plan_text)
        text.setReadOnly(True)
        text.setFont(get_mono_font(12))
        text.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {PANEL};
                color: {ACCENT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 12px;
                selection-background-color: #00e59933;
                selection-color: {TEXT_PRIMARY};
            }}
        """)
        layout.addWidget(text)