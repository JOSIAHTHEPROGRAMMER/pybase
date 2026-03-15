from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel



class TransactionStatusBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(28)
        self._build_ui()
        self.update_status(False)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)

        self.indicator = QLabel()
        self.indicator.setFixedSize(10, 10)
        self.indicator.setStyleSheet("border-radius: 5px; background-color: #9ca3af;")

        self.label = QLabel("No active transaction")
        self.label.setStyleSheet("font-size: 11px; color: #6b7280;")

        layout.addWidget(self.indicator)
        layout.addSpacing(6)
        layout.addWidget(self.label)
        layout.addStretch()

    def update_status(self, in_transaction: bool):
        """
        Update the indicator dot and label based on transaction state.
        Green dot = active transaction.
        Grey dot  = no transaction.
        """
        if in_transaction:
            self.indicator.setStyleSheet("border-radius: 5px; background-color: #16a34a;")
            self.label.setText("Transaction active — changes not yet committed")
            self.label.setStyleSheet("font-size: 11px; color: #16a34a; font-weight: bold;")
        else:
            self.indicator.setStyleSheet("border-radius: 5px; background-color: #9ca3af;")
            self.label.setText("No active transaction")
            self.label.setStyleSheet("font-size: 11px; color: #6b7280;")