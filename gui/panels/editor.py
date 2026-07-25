from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QLabel, QMessageBox
)

from PyQt6.QtCore import Qt
from gui.widgets.font import get_mono_font
from gui.widgets.highlighter import SQLHighlighter
from gui.widgets.history import QueryHistoryBar
from query.dispatch import execute_statement


BACKGROUND   = "#0f0f0f"
PANEL        = "#1a1a1a"
BORDER       = "#2e2e2e"
ACCENT       = "#00e599"
TEXT_PRIMARY = "#ededed"
TEXT_MUTED   = "#a0a0a0"
EDITOR_BG    = "#141414"


class EditorPanel(QWidget):
    def __init__(self, db, on_result, on_schema_change, on_transaction_change, on_explain):
        super().__init__()
        self.db = db
        self.on_result = on_result
        self.on_schema_change = on_schema_change
        self.on_transaction_change = on_transaction_change
        self.on_explain = on_explain
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

    def set_query(self, text: str):
        """
        Replace editor contents with the given query text.
        Used by the schema panel when a table is clicked.
        """
        self.editor.setPlainText(text)

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
        Rejoins cleaned lines into a single string, then splits on semicolons.

        Semicolons inside quoted strings are never treated as separators.
        A CREATE PROCEDURE statement additionally protects any semicolons
        inside its BEGIN...END body. This protection is scoped to
        statements that open with CREATE PROCEDURE specifically, since
        BEGIN also has an unrelated standalone meaning for starting a
        transaction elsewhere in the language.
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

        statements         = []
        current            = ""
        i                  = 0
        in_procedure_body  = False
        begin_depth        = 0

        while i < len(cleaned):
            char = cleaned[i]

            if char in ("'", '"'):
                quote = char
                current += char
                i += 1
                while i < len(cleaned) and cleaned[i] != quote:
                    current += cleaned[i]
                    i += 1
                if i < len(cleaned):
                    current += cleaned[i]
                    i += 1
                continue

            if not in_procedure_body and current.strip().upper().startswith("CREATE PROCEDURE"):
                if cleaned[i:i+5].upper() == "BEGIN" and self._is_word_boundary(cleaned, i, i + 5):
                    in_procedure_body = True
                    begin_depth = 1
                    current += cleaned[i:i+5]
                    i += 5
                    continue

            if in_procedure_body:
                if cleaned[i:i+5].upper() == "BEGIN" and self._is_word_boundary(cleaned, i, i + 5):
                    begin_depth += 1
                    current += cleaned[i:i+5]
                    i += 5
                    continue
                if cleaned[i:i+3].upper() == "END" and self._is_word_boundary(cleaned, i, i + 3):
                    begin_depth -= 1
                    current += cleaned[i:i+3]
                    i += 3
                    if begin_depth == 0:
                        in_procedure_body = False
                    continue

            if char == ";" and not in_procedure_body:
                if current.strip():
                    statements.append(current.strip())
                current = ""
                i += 1
                continue

            current += char
            i += 1

        if current.strip():
            statements.append(current.strip())

        return statements

    @staticmethod
    def _is_word_boundary(text: str, start: int, end: int) -> bool:
        before_ok = start == 0 or not text[start - 1].isalnum()
        after_ok  = end >= len(text) or not text[end].isalnum()
        return before_ok and after_ok


    def _execute_single(self, command: str) -> bool:
        """
        Execute a single SQL statement via the shared dispatch layer.
        Confirmation dialogs use QMessageBox for destructive operations.
        Returns True if successful, False if an error occurred.
        """
        return execute_statement(
            command,
            self.db,
            on_result=self.on_result,
            confirm=self._confirm_dialog,
            on_schema_change=self.on_schema_change,
            on_transaction_change=self.on_transaction_change,
            on_explain=self.on_explain,
        )

    def _confirm_dialog(self, title: str, text: str, informative: str) -> bool:
        confirm = QMessageBox(self)
        confirm.setWindowTitle(title)
        confirm.setText(text)
        confirm.setInformativeText(informative)
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return confirm.exec() == QMessageBox.StandardButton.Yes