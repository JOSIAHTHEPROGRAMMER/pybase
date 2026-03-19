from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox
)
from PyQt6.QtCore import Qt

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"

CHART_COLORS = [
    "#00e599", "#60a5fa", "#fbbf24",
    "#f87171", "#c084fc", "#34d399",
    "#fb923c", "#818cf8"
]

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class ChartPanel(QWidget):
    """
    Chart panel supporting bar, line, pie, scatter, and histogram charts.
    Automatically selects the best chart type for the data shape,
    or the user can pick manually from the dropdown.
    Requires at least one numeric column in the results to render.
    """

    CHART_TYPES = ["Auto", "Bar", "Line", "Pie", "Scatter", "Histogram"]

    def __init__(self):
        super().__init__()
        self._columns = []
        self._rows    = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        if not MATPLOTLIB_AVAILABLE:
            msg = QLabel(
                "Install matplotlib to enable charts:\n"
                "pip install matplotlib"
            )
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
            layout.addWidget(msg)
            return

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        chart_label = QLabel("Chart type")
        chart_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        toolbar.addWidget(chart_label)

        self.chart_selector = QComboBox()
        self.chart_selector.addItems(self.CHART_TYPES)
        self.chart_selector.setFixedWidth(130)
        self.chart_selector.setStyleSheet(f"""
            QComboBox {{
                background-color: {PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 12px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                selection-background-color: #00e59920;
                selection-color: {ACCENT};
            }}
        """)
        self.chart_selector.currentIndexChanged.connect(self._on_chart_type_changed)
        toolbar.addWidget(self.chart_selector)
        toolbar.addStretch()

        self.chart_hint = QLabel("")
        self.chart_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        toolbar.addWidget(self.chart_hint)

        layout.addLayout(toolbar)

        self.figure = Figure(facecolor=PANEL)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setStyleSheet(f"background-color: {PANEL};")
        layout.addWidget(self.canvas)

        self.placeholder = QLabel(
            "Run a SELECT with at least one numeric column to visualize results.\n\n"
            "Best results with one text column and one numeric column.\n"
            "Example: SELECT name, salary FROM employees ORDER BY salary DESC;"
        )
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(self.placeholder)

        self.canvas.hide()

    def _on_chart_type_changed(self, _index):
        """Re-render with the newly selected chart type when the dropdown changes."""
        if self._columns and self._rows:
            self._render(self._columns, self._rows)

    def update_chart(self, columns: list, rows: list):
        """
        Store latest query results and attempt to render a chart.
        Called from ResultsPanel every time a SELECT runs.
        """
        self._columns = columns
        self._rows    = rows
        self._render(columns, rows)

    def _classify_columns(self, columns, rows):
        """
        Inspect the first row of data to classify each column as
        numeric (int or float) or categorical (string).
        Returns two lists: str_cols and num_cols, each containing
        (index, column_name) tuples.
        """
        if not rows:
            return [], []

        str_cols = []
        num_cols = []

        for i, col in enumerate(columns):
            sample = rows[0][i]
            if isinstance(sample, (int, float)):
                num_cols.append((i, col))
            else:
                str_cols.append((i, col))

        return str_cols, num_cols

    def _style_ax(self, ax):
        """
        Apply the dark Neon theme to a matplotlib axes object.
        Sets background, spine, tick, and grid colors consistently.
        """
        ax.set_facecolor(PANEL)
        self.figure.patch.set_facecolor(PANEL)
        ax.tick_params(colors=TEXT_MUTED, labelsize=9)
        ax.spines["bottom"].set_color(BORDER)
        ax.spines["left"].set_color(BORDER)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.grid(True, color=BORDER, zorder=0, alpha=0.6)
        ax.set_axisbelow(True)

    def _render(self, columns, rows):
        """
        Decide which chart type to render based on the selector and data shape.
        Falls back to showing the placeholder if the data does not support
        the selected chart type.
        """
        if not MATPLOTLIB_AVAILABLE:
            return

        self.figure.clear()
        self.canvas.hide()
        self.placeholder.show()

        if not columns or not rows:
            return

        str_cols, num_cols = self._classify_columns(columns, rows)

        if not num_cols:
            self.chart_hint.setText("No numeric columns found")
            return

        selected = self.chart_selector.currentText()

        if selected == "Auto":
            selected = self._pick_best_type(str_cols, num_cols, rows)

        success = False

        if selected == "Bar":
            success = self._draw_bar(str_cols, num_cols, rows)
        elif selected == "Line":
            success = self._draw_line(str_cols, num_cols, rows)
        elif selected == "Pie":
            success = self._draw_pie(str_cols, num_cols, rows)
        elif selected == "Scatter":
            success = self._draw_scatter(num_cols, rows)
        elif selected == "Histogram":
            success = self._draw_histogram(num_cols, rows)

        if success:
            self.figure.tight_layout(pad=1.5)
            self.canvas.draw()
            self.canvas.show()
            self.placeholder.hide()
        else:
            self.chart_hint.setText(f"{selected} requires different data shape")

    def _pick_best_type(self, str_cols, num_cols, rows):
        """
        Choose the most appropriate chart type automatically based on data shape.

        One string + one numeric  ->  Bar
        Two or more numeric only  ->  Scatter
        One string + one numeric, few rows ->  Pie
        One numeric only          ->  Histogram
        Multiple rows + one numeric -> Line
        """
        has_str = len(str_cols) > 0
        num_count = len(num_cols)
        row_count = len(rows)

        if has_str and num_count == 1 and row_count <= 8:
            return "Pie"
        if has_str and num_count >= 1:
            return "Bar"
        if num_count >= 2:
            return "Scatter"
        if num_count == 1 and row_count > 10:
            return "Histogram"
        return "Line"

    def _draw_bar(self, str_cols, num_cols, rows):
        """
        Draw a bar chart.
        Uses the first string column as labels and the first numeric column as values.
        Falls back to row index as labels if no string column exists.
        """
        num_idx, num_name = num_cols[0]
        values = [row[num_idx] for row in rows]

        if str_cols:
            str_idx, str_name = str_cols[0]
            labels = [str(row[str_idx]) for row in rows]
        else:
            labels = [str(i + 1) for i in range(len(rows))]
            str_name = "Row"

        ax = self.figure.add_subplot(111)
        self._style_ax(ax)

        bars = ax.bar(labels, values, color=ACCENT, width=0.55, zorder=2)

        ax.set_xlabel(str_name if str_cols else "Row", color=TEXT_MUTED, fontsize=10)
        ax.set_ylabel(num_name, color=TEXT_MUTED, fontsize=10)
        ax.set_title(f"{num_name} by {str_name if str_cols else 'Row'}",
                     color=TEXT_PRIMARY, fontsize=11, pad=10)

        if len(labels) > 8:
            ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)

        max_val = max(values) if values else 1
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max_val * 0.012,
                str(val),
                ha="center", va="bottom",
                color=TEXT_PRIMARY, fontsize=8
            )

        return True

    def _draw_line(self, str_cols, num_cols, rows):
        """
        Draw a line chart.
        Plots each numeric column as a separate line.
        Uses the first string column or row index as the x axis.
        """
        ax = self.figure.add_subplot(111)
        self._style_ax(ax)

        if str_cols:
            str_idx, str_name = str_cols[0]
            x_labels = [str(row[str_idx]) for row in rows]
            x_vals   = list(range(len(rows)))
            ax.set_xlabel(str_name, color=TEXT_MUTED, fontsize=10)
        else:
            x_vals   = list(range(len(rows)))
            x_labels = [str(i + 1) for i in x_vals]
            ax.set_xlabel("Row", color=TEXT_MUTED, fontsize=10)

        for k, (num_idx, num_name) in enumerate(num_cols):
            values = [row[num_idx] for row in rows]
            color  = CHART_COLORS[k % len(CHART_COLORS)]
            ax.plot(x_vals, values, color=color, linewidth=2,
                    marker="o", markersize=5, label=num_name, zorder=3)

        ax.set_xticks(x_vals)
        ax.set_xticklabels(x_labels,
                           rotation=35 if len(x_labels) > 8 else 0,
                           ha="right" if len(x_labels) > 8 else "center",
                           fontsize=8)

        ax.set_title("Line Chart", color=TEXT_PRIMARY, fontsize=11, pad=10)

        if len(num_cols) > 1:
            ax.legend(
                facecolor=PANEL, edgecolor=BORDER,
                labelcolor=TEXT_PRIMARY, fontsize=9
            )

        return True

    def _draw_pie(self, str_cols, num_cols, rows):
        """
        Draw a pie chart.
        Uses the first numeric column as slice sizes.
        Uses the first string column as slice labels if available.
        Only renders if all values are positive.
        """
        num_idx, num_name = num_cols[0]
        values = [row[num_idx] for row in rows]

        if any(v <= 0 for v in values):
            return False

        if str_cols:
            str_idx, _ = str_cols[0]
            labels = [str(row[str_idx]) for row in rows]
        else:
            labels = [str(i + 1) for i in range(len(rows))]

        ax = self.figure.add_subplot(111)
        ax.set_facecolor(PANEL)
        self.figure.patch.set_facecolor(PANEL)

        colors = [CHART_COLORS[i % len(CHART_COLORS)] for i in range(len(values))]

        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=140,
            wedgeprops={"edgecolor": BACKGROUND, "linewidth": 1.5}
        )

        for text in texts:
            text.set_color(TEXT_PRIMARY)
            text.set_fontsize(9)

        for autotext in autotexts:
            autotext.set_color(BACKGROUND)
            autotext.set_fontsize(8)
            autotext.set_fontweight("bold")

        ax.set_title(f"{num_name} distribution",
                     color=TEXT_PRIMARY, fontsize=11, pad=10)

        return True

    def _draw_scatter(self, num_cols, rows):
        """
        Draw a scatter plot.
        Requires at least two numeric columns.
        Uses the first as x and the second as y.
        Additional numeric columns are ignored.
        """
        if len(num_cols) < 2:
            return False

        x_idx, x_name = num_cols[0]
        y_idx, y_name = num_cols[1]

        x_vals = [row[x_idx] for row in rows]
        y_vals = [row[y_idx] for row in rows]

        ax = self.figure.add_subplot(111)
        self._style_ax(ax)

        ax.scatter(
            x_vals, y_vals,
            color=ACCENT, s=60, alpha=0.85,
            edgecolors=BACKGROUND, linewidths=0.8,
            zorder=3
        )

        ax.set_xlabel(x_name, color=TEXT_MUTED, fontsize=10)
        ax.set_ylabel(y_name, color=TEXT_MUTED, fontsize=10)
        ax.set_title(f"{x_name} vs {y_name}",
                     color=TEXT_PRIMARY, fontsize=11, pad=10)

        return True

    def _draw_histogram(self, num_cols, rows):
        """
        Draw a histogram of the first numeric column.
        Bin count is automatically chosen based on the number of rows.
        Shows the distribution of values across the dataset.
        """
        num_idx, num_name = num_cols[0]
        values = [row[num_idx] for row in rows]

        bins = min(max(5, len(values) // 3), 20)

        ax = self.figure.add_subplot(111)
        self._style_ax(ax)

        ax.hist(
            values, bins=bins,
            color=ACCENT, edgecolor=BACKGROUND,
            linewidth=0.8, zorder=2, alpha=0.9
        )

        ax.set_xlabel(num_name, color=TEXT_MUTED, fontsize=10)
        ax.set_ylabel("Frequency", color=TEXT_MUTED, fontsize=10)
        ax.set_title(f"Distribution of {num_name}",
                     color=TEXT_PRIMARY, fontsize=11, pad=10)

        return True
