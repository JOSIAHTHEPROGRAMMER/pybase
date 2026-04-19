from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QLabel, QMessageBox
)

from PyQt6.QtCore import Qt
from gui.widgets.font import get_mono_font

from cli import (
    parse_create_table, parse_insert, parse_select,
    parse_delete, parse_update, parse_create_index,
    parse_drop_table, _detect_set_operator, resolve_subqueries
)
from gui.widgets.highlighter import SQLHighlighter
from gui.widgets.history import QueryHistoryBar

BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"
EDITOR_BG    = "#141414"


class EditorPanel(QWidget):
    def __init__(self, db, on_result, on_schema_change, on_transaction_change):
        super().__init__()
        self.db = db
        self.on_result = on_result
        self.on_schema_change = on_schema_change
        self.on_transaction_change = on_transaction_change
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)

        # Header row
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        label = QLabel("SQL Editor")
        label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-weight: 600; font-size: 13px;"
        )
        hint = QLabel("Ctrl+Enter to run  |  Ctrl+/ to comment")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(hint)
        layout.addLayout(header)

        # Query history dropdown sits above the editor
        self.history_bar = QueryHistoryBar(on_select=self._load_from_history)
        layout.addWidget(self.history_bar)

        layout.addSpacing(4)

        # SQL text editor
        self.editor = QPlainTextEdit()
        self.editor.setFont(get_mono_font(12))
        self.editor.setPlaceholderText(
            "-- Enter SQL here\n\n"
            "-- Examples:\n"
            "-- CREATE TABLE users (id int PRIMARY KEY, name string);\n"
            "-- INSERT INTO users VALUES (1, 'Alice');\n"
            "-- SELECT * FROM users WHERE id > 0 ORDER BY id ASC;\n"
            "-- BEGIN;\n"
            "-- SAVEPOINT sp1;\n"
            "-- ROLLBACK TO SAVEPOINT sp1;\n"
            "-- RELEASE SAVEPOINT sp1;\n"
            "-- COMMIT;"
        )
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {EDITOR_BG};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 10px;
                selection-background-color: #00e59933;
                selection-color: {TEXT_PRIMARY};
            }}
        """)

        # Attach syntax highlighter to editor document
        self.highlighter = SQLHighlighter(self.editor.document())

        # Override keypress to support Ctrl+Enter
        self.editor.keyPressEvent = self._editor_key_press
        layout.addWidget(self.editor)

        layout.addSpacing(6)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        self.run_btn = QPushButton("▶  Run Query")
        self.run_btn.setFixedHeight(36)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: #0a0a0a;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 20px;
            }}
            QPushButton:hover {{ background-color: #00d486; }}
            QPushButton:pressed {{ background-color: #00b870; }}
        """)
        self.run_btn.setToolTip(
            "Run all statements (Ctrl+Enter)\n"
            "Tip: select text to run only that selection"
        )
        self.run_btn.clicked.connect(self._run_query)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setFixedHeight(36)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 6px;
                font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                border-color: #555;
                color: {TEXT_PRIMARY};
            }}
        """)
        self.clear_btn.clicked.connect(self.editor.clear)

        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addSpacing(4)

    def _editor_key_press(self, event):
        """
        Ctrl+Enter triggers query execution.
        Ctrl+/ toggles line comments on selected lines or current line.
        All other keypresses are handled normally.
        """
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self._run_query()

        elif (
            event.key() == Qt.Key.Key_Slash
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self._toggle_comment()

        else:
            QPlainTextEdit.keyPressEvent(self.editor, event)

    def _toggle_comment(self):
        """
        Toggle SQL comment prefix on selected lines or the current line.
        If all selected lines start with -- they are uncommented.
        Otherwise all selected lines are commented.
        Works on single lines and multi-line selections.
        """
        cursor = self.editor.textCursor()
        doc    = self.editor.document()

        start_block = doc.findBlock(cursor.selectionStart()).blockNumber()
        end_block   = doc.findBlock(cursor.selectionEnd()).blockNumber()

        # Collect all lines in selection
        lines = []
        for block_num in range(start_block, end_block + 1):
            block = doc.findBlockByNumber(block_num)
            lines.append(block.text())

        # Decide whether to comment or uncomment
        # If every non-empty line already starts with -- then uncomment
        all_commented = all(
            line.lstrip().startswith("--")
            for line in lines
            if line.strip()
        )

        # Apply transformation
        cursor.beginEditBlock()

        for block_num in range(start_block, end_block + 1):
            block       = self.editor.document().findBlockByNumber(block_num)
            block_text  = block.text()
            block_cursor = self.editor.textCursor()
            block_cursor.setPosition(block.position())
            block_cursor.movePosition(
                block_cursor.MoveOperation.EndOfBlock,
                block_cursor.MoveMode.KeepAnchor
            )

            if all_commented:
                # Remove leading -- and one optional space
                stripped = block_text.lstrip()
                if stripped.startswith("-- "):
                    new_text = block_text.replace("-- ", "", 1)
                elif stripped.startswith("--"):
                    new_text = block_text.replace("--", "", 1)
                else:
                    new_text = block_text
            else:
                # Add -- at the start of non-empty lines
                if block_text.strip():
                    new_text = "-- " + block_text
                else:
                    new_text = block_text

            block_cursor.insertText(new_text)

        cursor.endEditBlock()

    def _load_from_history(self, query: str):
        """Load a historical query back into the editor."""
        self.editor.setPlainText(query)

    def _run_query(self):
        """
        Parse and execute SQL from the editor.
        If text is selected, only the selected text is executed.
        Otherwise the full editor content is executed.
        Statements are split by semicolons and comment lines are stripped.
        Each statement runs independently and errors stop execution.
        """
        cursor = self.editor.textCursor()

        # If user has selected text, run only that selection
        if cursor.hasSelection():
            raw = cursor.selectedText().strip()
            # Qt uses unicode paragraph separator for newlines in selections
            raw = raw.replace("\u2029", "\n")
        else:
            raw = self.editor.toPlainText().strip()

        if not raw:
            return

        self.history_bar.add(raw)

        statements = self._parse_statements(raw)

        if not statements:
            return

        for statement in statements:
            success = self._execute_single(statement)
            if not success:
                break

    def _parse_statements(self, raw: str) -> list:
        """
        Split raw editor text into individual SQL statements.

        Strips comment lines starting with double dash.
        Strips inline comments from end of lines.
        Rejoins cleaned lines and splits on semicolons.
        Skips empty results.
        """
        lines = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            if "--" in stripped:
                stripped = stripped[:stripped.index("--")].strip()
            lines.append(stripped)

        cleaned = " ".join(lines)
        parts = cleaned.split(";")

        return [p.strip() for p in parts if p.strip()]

    def _execute_single(self, command: str) -> bool:
        """
        Execute a single SQL statement.
        Returns True if successful, False if an error occurred.
        All results and errors are passed to the on_result callback.

        SAVEPOINT variants are checked before plain ROLLBACK so that
        "ROLLBACK TO SAVEPOINT" is never swallowed by the ROLLBACK branch.
        """
        cmd_upper = command.upper().strip()

        try:
            if cmd_upper == "BEGIN":
                self.db.begin_transaction()
                self.on_transaction_change()
                self.on_result([], [], "Transaction started.")

            elif cmd_upper == "COMMIT":
                results = self.db.commit_transaction()
                self.on_transaction_change()
                self.on_result([], [], "Transaction committed.\n" + "\n".join(results))

            # SAVEPOINT branches must appear before the plain ROLLBACK check
            # because "ROLLBACK TO SAVEPOINT" starts with "ROLLBACK"
            elif cmd_upper.startswith("ROLLBACK TO SAVEPOINT"):
                # Extract savepoint name from: ROLLBACK TO SAVEPOINT <name>
                name = command.strip().split()[-1]
                self.db.current_transaction.rollback_to_savepoint(name)
                self.on_result([], [], f"Rolled back to savepoint '{name}'.")

            elif cmd_upper.startswith("RELEASE SAVEPOINT"):
                # Extract savepoint name from: RELEASE SAVEPOINT <name>
                name = command.strip().split()[-1]
                self.db.current_transaction.release_savepoint(name)
                self.on_result([], [], f"Savepoint '{name}' released.")

            elif cmd_upper.startswith("SAVEPOINT"):
                # Extract savepoint name from: SAVEPOINT <name>
                name = command.strip().split()[-1]
                self.db.current_transaction.savepoint(name)
                self.on_result([], [], f"Savepoint '{name}' created.")

            elif cmd_upper == "ROLLBACK":
                self.db.rollback_transaction()
                self.on_transaction_change()
                self.on_result([], [], "Transaction rolled back.")

            elif cmd_upper.startswith("CREATE INDEX"):
                table_name, column_name = parse_create_index(command)
                table = self.db.get_table(table_name)
                msg = table.create_index(column_name)
                self.on_schema_change()
                self.on_result([], [], msg)

            elif cmd_upper.startswith("CREATE TABLE"):
                (table_name, columns, unique_columns, primary_key,
                foreign_keys, not_null_columns, default_values,
                check_constraints, auto_increment_col) = parse_create_table(command)

                table = self.db.create_table(table_name, columns)

                for col in unique_columns:
                    table.add_unique_constraint(col)

                if primary_key:
                    table.set_primary_key(primary_key)

                for col in not_null_columns:
                    table.add_not_null_constraint(col)

                for col, val in default_values.items():
                    table.set_default_value(col, val)

                for cc in check_constraints:
                    table.add_check_constraint(cc["column"], cc["op"], cc["value"])

                for fk in foreign_keys:
                    table.add_foreign_key(
                        fk["column"],
                        fk["ref_table"],
                        fk["ref_column"],
                        on_delete=fk.get("on_delete"),
                        on_update=fk.get("on_update")
                    )

                if auto_increment_col:
                    table.set_auto_increment(auto_increment_col)

                self.on_schema_change()
                self.on_result([], [], f"Table '{table_name}' created successfully.")

            elif cmd_upper.startswith("DROP DATABASE"):
                if self.db.in_transaction():
                    raise ValueError(
                        "Cannot DROP DATABASE inside a transaction. "
                        "COMMIT or ROLLBACK first."
                    )

                # Stricter confirm dialog since this destroys everything
                confirm = QMessageBox(self)
                confirm.setWindowTitle("Confirm DROP DATABASE")
                confirm.setText("Drop the entire database?")
                confirm.setInformativeText(
                    "This will permanently delete ALL tables, ALL data, and query history. "
                    "This cannot be undone."
                )
                confirm.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
                )
                confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
                confirm.setStyleSheet("""
                    QMessageBox {
                        background-color: #1a1a1a;
                        color: #ededed;
                    }
                    QLabel { color: #ededed; }
                    QPushButton {
                        background-color: #2e2e2e;
                        color: #ededed;
                        border: 1px solid #444;
                        border-radius: 4px;
                        padding: 6px 16px;
                        min-width: 80px;
                    }
                    QPushButton:hover { background-color: #7f1d1d; }
                """)

                if confirm.exec() != QMessageBox.StandardButton.Yes:
                    self.on_result([], [], "DROP DATABASE cancelled.")
                    return True

                self.db.drop_database()
                self.on_schema_change()
                self.history_bar._clear()
                self.on_result([], [], "Database dropped. All tables and data deleted.")

            elif cmd_upper.startswith("DROP TABLE"):
                if self.db.in_transaction():
                    raise ValueError("Cannot DROP TABLE inside a transaction.")
                table_name = parse_drop_table(command)

                # Confirm before destroying data, destructive and irreversible
                confirm = QMessageBox(self)
                confirm.setWindowTitle("Confirm DROP TABLE")
                confirm.setText(f"Drop table '{table_name}'?")
                confirm.setInformativeText(
                    "This will permanently delete the table and all its data. "
                    "This cannot be undone."
                )
                confirm.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
                )
                confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
                confirm.setStyleSheet("""
                    QMessageBox {
                        background-color: #1a1a1a;
                        color: #ededed;
                    }
                    QLabel { color: #ededed; }
                    QPushButton {
                        background-color: #2e2e2e;
                        color: #ededed;
                        border: 1px solid #444;
                        border-radius: 4px;
                        padding: 6px 16px;
                        min-width: 80px;
                    }
                    QPushButton:hover { background-color: #3a3a3a; }
                """)

                if confirm.exec() != QMessageBox.StandardButton.Yes:
                    self.on_result([], [], "DROP TABLE cancelled.")
                    return True

                self.db.drop_table(table_name)
                self.on_schema_change()
                self.on_result([], [], f"Table '{table_name}' dropped.")

            elif cmd_upper.startswith("INSERT INTO"):
                table_name, row = parse_insert(command)
                if self.db.in_transaction():
                    self.db.current_transaction.add("insert", table_name, row=row)
                    self.on_result([], [], f"Queued: INSERT into '{table_name}'.")
                else:
                    # Pass db so FK constraints can be validated
                    self.db.get_table(table_name).insert(row, db=self.db)
                    self.on_result([], [], f"Row inserted into '{table_name}'.")

            elif cmd_upper.startswith("SELECT"):
                set_op = _detect_set_operator(command)
                if set_op:
                    rows, col_names = self._execute_set_operation(set_op)
                else:
                    (table_name, selected_columns, conditions,
                    order_by, limit, distinct, group_by, having) = parse_select(command)
                    rows, col_names = self._execute_select(
                        table_name, selected_columns, conditions,
                        order_by, limit, distinct, group_by, having
                    )
                self.on_result(col_names, rows, f"{len(rows)} row(s) returned.")

            elif cmd_upper.startswith("DELETE FROM"):
                table_name, conditions = parse_delete(command)
                if self.db.in_transaction():
                    self.db.current_transaction.add("delete", table_name, conditions=conditions)
                    self.on_result([], [], f"Queued: DELETE from '{table_name}'.")
                else:
                    count = self.db.get_table(table_name).delete(conditions, db=self.db)
                    self.on_result([], [], f"{count} row(s) deleted from '{table_name}'.")

            elif cmd_upper.startswith("UPDATE"):
                table_name, assignments, conditions = parse_update(command)
                if self.db.in_transaction():
                    self.db.current_transaction.add(
                        "update", table_name,
                        assignments=assignments,
                        conditions=conditions
                    )
                    self.on_result([], [], f"Queued: UPDATE '{table_name}'.")
                else:
                    # Pass db so FK constraints can be validated
                    count = self.db.get_table(table_name).update(
                        assignments, conditions, db=self.db
                    )
                    self.on_result([], [], f"{count} row(s) updated in '{table_name}'.")

            else:
                self.on_result([], [], f"Unsupported command: {command[:40]}")

            return True

        except Exception as e:
            self.on_result([], [], f"Error in '{command[:40]}...': {e}")
            return False


    def _execute_select(self, table_name, selected_columns, conditions,
                        order_by, limit, distinct, group_by, having):
        """
        Resolve subqueries in conditions, then run select_aggregate or
        select_advanced depending on whether GROUP BY is present.
        Returns (rows, col_names).
        """
        table = self.db.get_table(table_name)

        # Resolve subqueries inside conditions before evaluation
        resolve_subqueries(conditions, self.db)
        
        if group_by:
            rows = table.select_aggregate(selected_columns, conditions, group_by, having)
        else:
            rows = table.select_advanced(
                selected_columns, conditions, order_by, limit, distinct=distinct
            )

        if selected_columns == ["*"]:
            col_names = [col[0] for col in table.columns]
        else:
            col_names = selected_columns

        return rows, col_names



    def _execute_set_operation(self, set_op):
        """
        Execute UNION, UNION ALL, INTERSECT, or EXCEPT.
        Parses and executes each side independently then merges.
        Returns (rows, col_names).
        """
        operator, left_sql, right_sql = set_op

        (lt, lc, lcond, lo, ll, ld, lg, lh) = parse_select(left_sql)
        (rt, rc, rcond, ro, rl, rd, rg, rh) = parse_select(right_sql)

        left_rows,  col_names = self._execute_select(lt, lc, lcond, lo, ll, ld, lg, lh)
        right_rows, _         = self._execute_select(rt, rc, rcond, ro, rl, rd, rg, rh)

        if operator == "UNION ALL":
            result = left_rows + right_rows

        elif operator == "UNION":
            seen   = []
            result = []
            for row in left_rows + right_rows:
                if row not in seen:
                    seen.append(row)
                    result.append(row)

        elif operator == "INTERSECT":
            seen, result = [], []
            for row in left_rows:
                if row in right_rows and row not in seen:
                    seen.append(row)
                    result.append(row)

        elif operator == "EXCEPT":
            seen, result = [], []
            for row in left_rows:
                if row not in right_rows and row not in seen:
                    seen.append(row)
                    result.append(row)
        else:
            result = left_rows

        return result, col_names
    




