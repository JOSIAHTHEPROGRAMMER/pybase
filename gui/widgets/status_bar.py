from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt

BACKGROUND   = "#0f0f0f"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"


class TransactionStatusBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(30)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BACKGROUND};
                border-top: 1px solid {BORDER};
            }}
        """)
        self._build_ui()
        self.update_status(False)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        self.indicator = QLabel("●")
        self.indicator.setFixedWidth(16)

        self.label = QLabel()
        self.label.setStyleSheet(f"font-size: 11px; border: none;")

        layout.addWidget(self.indicator)
        layout.addSpacing(4)
        layout.addWidget(self.label)
        layout.addStretch()

    def update_status(self, in_transaction: bool):
        """
        Update the indicator and label based on transaction state.
        Green = active transaction.
        Grey  = no active transaction.
        """
        if in_transaction:
            self.indicator.setStyleSheet(f"color: {ACCENT}; font-size: 10px; border: none;")
            self.label.setText("Transaction active -changes not yet committed")
            self.label.setStyleSheet(f"font-size: 11px; color: {ACCENT}; border: none;")
        else:
            self.indicator.setStyleSheet(f"color: #444; font-size: 10px; border: none;")
            self.label.setText("No active transaction")
            self.label.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; border: none;")
