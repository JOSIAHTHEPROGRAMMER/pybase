from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
import re


class SQLHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for the SQL editor.
    Applies color rules to keywords, types, strings, numbers, and comments.
    Extends QSyntaxHighlighter. Qt calls highlightBlock on each line automatically.
    """

    COLOR_KEYWORD = "#00e599"
    COLOR_TYPE    = "#60a5fa"
    COLOR_STRING  = "#fbbf24"
    COLOR_NUMBER  = "#f87171"
    COLOR_COMMENT = "#555555"

    KEYWORDS = [
        # Core DML
        "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES",
        "UPDATE", "SET", "DELETE",
        # DDL
        "CREATE", "TABLE", "DROP", "INDEX", "DATABASE",
        # Constraints and keys
        "ON", "PRIMARY", "KEY", "UNIQUE", "FOREIGN",
        "REFERENCES", "AUTO_INCREMENT", "DEFAULT", "CHECK",
        # Filtering and ordering
        "WHERE", "ORDER", "BY", "ASC", "DESC", "LIMIT",
        "AND", "OR", "NOT", "NULL", "IS", "IN", "LIKE", "BETWEEN",
        # Transactions and savepoints
        "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE",
        # Boolean literals
        "TRUE", "FALSE",
        # Batch C: query system
        "DISTINCT",
        "AS",
        "UNION", "INTERSECT", "EXCEPT", "ALL",
        "GROUP", "HAVING",
        "EXISTS", "ANY",
        "COUNT", "SUM", "AVG", "MIN", "MAX",
    ]

    TYPES = ["INT", "BIGINT", "FLOAT", "BOOLEAN", "BOOL", "STRING"]

    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        self._build_rules()

    def _fmt(self, color: str, bold: bool = False) -> QTextCharFormat:
        """Build a QTextCharFormat with the given color and optional bold."""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    def _build_rules(self):
        keyword_fmt = self._fmt(self.COLOR_KEYWORD, bold=True)
        for kw in self.KEYWORDS:
            self.rules.append((
                re.compile(rf"\b{kw}\b", re.IGNORECASE),
                keyword_fmt
            ))

        type_fmt = self._fmt(self.COLOR_TYPE)
        for t in self.TYPES:
            self.rules.append((
                re.compile(rf"\b{t}\b", re.IGNORECASE),
                type_fmt
            ))

        # Single-quoted strings
        self.rules.append((
            re.compile(r"'[^']*'"),
            self._fmt(self.COLOR_STRING)
        ))

        # Numeric literals
        self.rules.append((
            re.compile(r"\b\d+(\.\d+)?\b"),
            self._fmt(self.COLOR_NUMBER)
        ))

        # Single-line comments
        self.rules.append((
            re.compile(r"--[^\n]*"),
            self._fmt(self.COLOR_COMMENT)
        ))

    def highlightBlock(self, text: str):
        """
        Called by Qt automatically for each line of text.
        Applies all rules in order. Later rules override earlier ones.
        """
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(
                    match.start(),
                    match.end() - match.start(),
                    fmt
                )