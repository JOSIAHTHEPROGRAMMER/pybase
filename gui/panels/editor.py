from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QLabel
)
from PyQt6.QtGui import QFont

from cli import (
    parse_create_table, parse_insert, parse_select,
    parse_delete, parse_update, parse_create_index,
    parse_drop_table
)


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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Label
        label = QLabel("SQL Editor")
        label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(label)

        # SQL text editor
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Courier New", 11))
        self.editor.setPlaceholderText(
            "Enter SQL here...\n\n"
            "Examples:\n"
            "  CREATE TABLE users (id int PRIMARY KEY, name string);\n"
            "  INSERT INTO users VALUES (1, 'Alice');\n"
            "  SELECT * FROM users WHERE id > 0 ORDER BY id ASC LIMIT 10;\n"
            "  BEGIN;\n"
            "  COMMIT;"
        )
        layout.addWidget(self.editor)

        # Button row
        btn_layout = QHBoxLayout()

        self.run_btn = QPushButton("▶  Run")
        self.run_btn.setFixedHeight(34)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                border-radius: 5px;
                font-size: 13px;
                padding: 0 18px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:pressed { background-color: #1e40af; }
        """)
        self.run_btn.clicked.connect(self._run_query)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setFixedHeight(34)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5e7eb;
                color: #111827;
                border-radius: 5px;
                font-size: 13px;
                padding: 0 18px;
            }
            QPushButton:hover { background-color: #d1d5db; }
        """)
        self.clear_btn.clicked.connect(self.editor.clear)

        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _run_query(self):
        """
        Parse and execute the SQL in the editor.
        Dispatches to the correct handler based on the command keyword.
        Reuses the same parse functions as the CLI — single source of truth.
        """
        command = self.editor.toPlainText().strip()
        if not command:
            return

        cmd_upper = command.upper().rstrip(";").strip()

        try:
            if cmd_upper in ("BEGIN",):
                self.db.begin_transaction()
                self.on_transaction_change()
                self.on_result([], [], "Transaction started.")

            elif cmd_upper in ("COMMIT",):
                results = self.db.commit_transaction()
                self.on_transaction_change()
                self.on_result([], [], "Transaction committed.\n" + "\n".join(results))

            elif cmd_upper in ("ROLLBACK",):
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
                table_name, columns, unique_columns, primary_key = parse_create_table(command)
                table = self.db.create_table(table_name, columns)
                for col in unique_columns:
                    table.add_unique_constraint(col)
                if primary_key:
                    table.set_primary_key(primary_key)
                self.on_schema_change()
                self.on_result([], [], f"Table '{table_name}' created successfully.")

            elif cmd_upper.startswith("DROP TABLE"):
                if self.db.in_transaction():
                    raise ValueError("Cannot DROP TABLE inside a transaction.")
                table_name = parse_drop_table(command)
                self.db.drop_table(table_name)
                self.on_schema_change()
                self.on_result([], [], f"Table '{table_name}' dropped.")

            elif cmd_upper.startswith("INSERT INTO"):
                table_name, row = parse_insert(command)
                if self.db.in_transaction():
                    self.db.current_transaction.add("insert", table_name, row=row)
                    self.on_result([], [], f"Queued: INSERT into '{table_name}'.")
                else:
                    self.db.get_table(table_name).insert(row)
                    self.on_result([], [], f"Row inserted into '{table_name}'.")

            elif cmd_upper.startswith("SELECT"):
                table_name, selected_columns, conditions, order_by, limit = parse_select(command)
                table = self.db.get_table(table_name)
                rows = table.select_advanced(selected_columns, conditions, order_by, limit)

                # Determine display column headers
                if selected_columns == ["*"]:
                    col_names = [col[0] for col in table.columns]
                else:
                    col_names = selected_columns

                self.on_result(col_names, rows, f"{len(rows)} row(s) returned.")

            elif cmd_upper.startswith("DELETE FROM"):
                table_name, conditions = parse_delete(command)
                if self.db.in_transaction():
                    self.db.current_transaction.add("delete", table_name, conditions=conditions)
                    self.on_result([], [], f"Queued: DELETE from '{table_name}'.")
                else:
                    count = self.db.get_table(table_name).delete(conditions)
                    self.on_result([], [], f"{count} row(s) deleted from '{table_name}'.")

            elif cmd_upper.startswith("UPDATE"):
                table_name, assignments, conditions = parse_update(command)
                if self.db.in_transaction():
                    self.db.current_transaction.add(
                        "update", table_name,
                        assignments=assignments, conditions=conditions
                    )
                    self.on_result([], [], f"Queued: UPDATE '{table_name}'.")
                else:
                    count = self.db.get_table(table_name).update(assignments, conditions)
                    self.on_result([], [], f"{count} row(s) updated in '{table_name}'.")

            else:
                self.on_result([], [], "Unsupported command.")

        except Exception as e:
            self.on_result([], [], f"Error: {e}")