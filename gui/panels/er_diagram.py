from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"
FK_COLOR     = "#60a5fa"

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import FancyBboxPatch
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class ERDiagramPanel(QWidget):
    """
    Entity Relationship diagram panel.

    Renders a live diagram of all tables and their columns.
    Detects foreign key relationships by matching columns named
    <table>_id or <table>id to primary keys in other tables.
    Draws crow foot notation on relationship lines.
    Refreshes automatically after every DDL operation.
    """

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._build_ui()

    def _build_ui(self):
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(8, 8, 8, 8)

        if not MATPLOTLIB_AVAILABLE:
            msg = QLabel(
                "Install matplotlib to enable ER diagrams:\n"
                "pip install matplotlib"
            )
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
            self.layout_.addWidget(msg)
            return

        self.figure = Figure(facecolor=BACKGROUND)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setStyleSheet(f"background-color: {BACKGROUND};")
        self.layout_.addWidget(self.canvas)

        self.placeholder = QLabel(
            "No tables yet.\n\nCreate a table to see the ER diagram."
        )
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.layout_.addWidget(self.placeholder)

        self.refresh()

    def _detect_relationships(self):
        """
        Read foreign key relationships directly from table schema.
        No naming convention guessing - only real FK constraints
        registered via REFERENCES are shown.

        Returns a list of tuples:
            (from_table, from_col, to_table, to_col)
        where from_table is the many side and to_table is the one side.
        """
        relationships = []

        for table_name, table in self.db.tables.items():
            for fk in table.foreign_keys:
                relationships.append((
                    table_name,
                    fk["column"],
                    fk["ref_table"],
                    fk["ref_column"]
                ))

        return relationships

    def _draw_crow_foot(self, ax, x, y, direction, color):
        """
        Draw a crow foot symbol representing the many side of a relationship.
        The foot consists of three lines fanning outward from a point.
        A vertical bar is drawn just inside the foot for the mandatory marker.
        Direction is either left or right indicating which way the foot faces.
        """
        size  = 0.22
        bar_x = 0.10

        if direction == "right":
            ax.plot([x + bar_x, x + bar_x], [y - 0.09, y + 0.09],
                    color=color, linewidth=1.8, zorder=7, solid_capstyle="round")
            ax.plot([x, x + size], [y, y],
                    color=color, linewidth=1.4, zorder=7)
            ax.plot([x, x + size], [y, y + 0.11],
                    color=color, linewidth=1.4, zorder=7)
            ax.plot([x, x + size], [y, y - 0.11],
                    color=color, linewidth=1.4, zorder=7)
        else:
            ax.plot([x - bar_x, x - bar_x], [y - 0.09, y + 0.09],
                    color=color, linewidth=1.8, zorder=7, solid_capstyle="round")
            ax.plot([x, x - size], [y, y],
                    color=color, linewidth=1.4, zorder=7)
            ax.plot([x, x - size], [y, y + 0.11],
                    color=color, linewidth=1.4, zorder=7)
            ax.plot([x, x - size], [y, y - 0.11],
                    color=color, linewidth=1.4, zorder=7)

    def _draw_one_marker(self, ax, x, y, direction, color):
        """
        Draw a double vertical bar representing the one side of a relationship.
        Two parallel vertical lines are drawn near the connection point.
        Direction is either left or right indicating which side the table is on.
        """
        g1 = 0.07
        g2 = 0.14

        if direction == "right":
            ax.plot([x + g1, x + g1], [y - 0.09, y + 0.09],
                    color=color, linewidth=1.8, zorder=7, solid_capstyle="round")
            ax.plot([x + g2, x + g2], [y - 0.09, y + 0.09],
                    color=color, linewidth=1.8, zorder=7, solid_capstyle="round")
        else:
            ax.plot([x - g1, x - g1], [y - 0.09, y + 0.09],
                    color=color, linewidth=1.8, zorder=7, solid_capstyle="round")
            ax.plot([x - g2, x - g2], [y - 0.09, y + 0.09],
                    color=color, linewidth=1.8, zorder=7, solid_capstyle="round")

    def refresh(self):
        """
        Redraw the full ER diagram from the current database state.
        Called after every DDL operation via ResultsPanel.refresh_er.
        Clears the figure completely before redrawing.
        """
        if not MATPLOTLIB_AVAILABLE:
            return

        self.figure.clear()
        tables = list(self.db.tables.items())

        if not tables:
            self.canvas.hide()
            self.placeholder.show()
            return

        self.placeholder.hide()
        self.canvas.show()

        ax = self.figure.add_subplot(111)
        ax.set_facecolor(BACKGROUND)
        self.figure.patch.set_facecolor(BACKGROUND)
        ax.axis("off")

        relationships = self._detect_relationships()
      #  print(f"Detected relationships: {relationships}")

        fk_columns = {
            (from_table, from_col)
            for from_table, from_col, _, _ in relationships
        }

        cols_per_row = 3
        box_w        = 3.2
        header_h     = 0.45
        row_h        = 0.36
        col_gap      = 1.8
        row_gap      = 1.2
        pad          = 0.20

        sorted_tables = sorted(self.db.tables.items())
        max_cols      = max(len(t.columns) for _, t in sorted_tables)

        box_meta = {}

        for i, (table_name, table) in enumerate(sorted_tables):
            col_pos = i % cols_per_row
            row_pos = i // cols_per_row

            box_h = header_h + pad * 2 + len(table.columns) * row_h
            x     = col_pos * (box_w + col_gap)
            y     = -(row_pos * (max_cols * row_h + header_h + pad * 2 + row_gap))

            box_meta[table_name] = (x, y, box_w, box_h)

        for table_name, table in sorted_tables:
            x, y, w, h = box_meta[table_name]

            outer = FancyBboxPatch(
                (x, y - h), w, h,
                boxstyle="round,pad=0.05",
                facecolor=PANEL,
                edgecolor=BORDER,
                linewidth=1.5,
                zorder=2
            )
            ax.add_patch(outer)

            header_bar = FancyBboxPatch(
                (x, y - header_h), w, header_h,
                boxstyle="round,pad=0.03",
                facecolor="#0d1f1a",
                edgecolor=ACCENT,
                linewidth=1.8,
                zorder=3
            )
            ax.add_patch(header_bar)

            ax.text(
                x + w / 2, y - header_h / 2,
                table_name,
                ha="center", va="center",
                fontsize=10, fontweight="bold",
                color=ACCENT, zorder=4
            )

            for j, (col_name, col_type) in enumerate(table.columns):
                cy = y - header_h - pad - j * row_h - row_h / 2

                is_pk = col_name == table.primary_key
                is_fk = (table_name, col_name) in fk_columns
                is_uq = col_name in table.unique_columns and not is_pk

                if is_pk:
                    col_color = ACCENT
                    label_prefix = "PK  "
                elif is_fk:
                    col_color = FK_COLOR
                    label_prefix = "FK  "
                else:
                    col_color = TEXT_PRIMARY
                    label_prefix = "      "

                tags = []
                if is_uq:
                    tags.append("UQ")
                if table.index_manager.has_index(col_name):
                    tags.append("IDX")

                badge = f"  [{', '.join(tags)}]" if tags else ""

                ax.text(
                    x + 0.18, cy,
                    f"{label_prefix}{col_name}{badge}",
                    ha="left", va="center",
                    fontsize=8.5, color=col_color, zorder=4
                )

                ax.text(
                    x + w - 0.14, cy,
                    col_type,
                    ha="right", va="center",
                    fontsize=8, color=TEXT_MUTED,
                    style="italic", zorder=4
                )

                if j < len(table.columns) - 1:
                    sep_y = cy - row_h / 2
                    ax.plot(
                        [x + 0.10, x + w - 0.10],
                        [sep_y, sep_y],
                        color=BORDER, linewidth=0.5, zorder=3
                    )

        for from_table, from_col, to_table, to_col in relationships:
            if from_table not in box_meta or to_table not in box_meta:
                continue

            fx, fy, fw, fh = box_meta[from_table]
            tx, ty, tw, th = box_meta[to_table]

            from_table_obj = self.db.tables[from_table]
            fk_idx = next(
                (i for i, (c, _) in enumerate(from_table_obj.columns) if c == from_col),
                0
            )
            fk_cy = fy - header_h - pad - fk_idx * row_h - row_h / 2

            to_table_obj = self.db.tables[to_table]
            pk_idx = next(
                (i for i, (c, _) in enumerate(to_table_obj.columns) if c == to_col),
                0
            )
            pk_cy = ty - header_h - pad - pk_idx * row_h - row_h / 2

            fk_center_x = fx + fw / 2
            pk_center_x = tx + tw / 2

            if fk_center_x > pk_center_x:
                x_from     = fx
                x_to       = tx + tw
                crow_dir   = "left"
                one_dir    = "right"
            else:
                x_from     = fx + fw
                x_to       = tx
                crow_dir   = "right"
                one_dir    = "left"

            mid_x = (x_from + x_to) / 2

            ax.plot(
                [x_from, mid_x],
                [fk_cy, fk_cy],
                color=FK_COLOR, linewidth=1.4,
                linestyle="dashed", zorder=5, alpha=0.85
            )
            ax.plot(
                [mid_x, mid_x],
                [fk_cy, pk_cy],
                color=FK_COLOR, linewidth=1.4,
                linestyle="dashed", zorder=5, alpha=0.85
            )
            ax.plot(
                [mid_x, x_to],
                [pk_cy, pk_cy],
                color=FK_COLOR, linewidth=1.4,
                linestyle="dashed", zorder=5, alpha=0.85
            )

            self._draw_crow_foot(ax, x_from, fk_cy, crow_dir, FK_COLOR)
            self._draw_one_marker(ax, x_to, pk_cy, one_dir, FK_COLOR)

        if box_meta:
            all_x_min = min(v[0] for v in box_meta.values())
            all_x_max = max(v[0] + v[2] for v in box_meta.values())
            all_y_max = max(v[1] for v in box_meta.values())
            all_y_min = min(v[1] - v[3] for v in box_meta.values())

            ax.set_xlim(all_x_min - 0.8, all_x_max + 0.8)
            ax.set_ylim(all_y_min - 0.6, all_y_max + 0.6)

        self.figure.tight_layout()
        self.canvas.draw()