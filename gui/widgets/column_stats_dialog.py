from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt

from gui.widgets.font import get_mono_font

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"


class ColumnStatsDialog(QDialog):
    """
    Non-modal window showing summary statistics for one column.
    Stays open alongside the main window, same pattern as ExplainDialog.
    """

    def __init__(self, table_name: str, stats: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Column Stats")
        self.setMinimumSize(360, 220)
        self.resize(400, 260)
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

        header = QLabel(f"{table_name}.{stats['column']}  ({stats['type']})")
        header.setStyleSheet(
            f"color: {ACCENT}; font-size: 13px; font-weight: 600;"
        )
        layout.addWidget(header)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {BORDER}; max-height: 1px; border: none;")
        layout.addWidget(divider)

        rows = [("Count", stats["count"]), ("Nulls", stats["nulls"])]

        if "min" in stats:
            rows.append(("Min", stats["min"]))
            rows.append(("Max", stats["max"]))
            rows.append(("Avg", f"{stats['avg']:.4f}" if stats["avg"] is not None else None))
        else:
            rows.append(("Distinct", stats["distinct"]))

        for label, value in rows:
            row_label = QLabel(f"{label}:  {value}")
            row_label.setFont(get_mono_font(12))
            row_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
            layout.addWidget(row_label)

        if "value_counts" in stats:
            breakdown_label = QLabel("Value breakdown")
            breakdown_label.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; margin-top: 6px;"
            )
            layout.addWidget(breakdown_label)

            for val, count in stats["value_counts"].items():
                item_label = QLabel(f"  {val}:  {count}")
                item_label.setFont(get_mono_font(11))
                item_label.setStyleSheet(f"color: {TEXT_MUTED};")
                layout.addWidget(item_label)

        layout.addStretch()