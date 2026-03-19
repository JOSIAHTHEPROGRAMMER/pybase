from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
import re


class SQLHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for the SQL editor.
    Applies color rules to keywords, types, strings, numbers, and comments.
    Extends QSyntaxHighlighter - Qt calls highlightBlock() on each line automatically.
    """

    # Neon palette
    COLOR_KEYWORD = "#00e599"  # accent green - SELECT, FROM, WHERE etc.
    COLOR_TYPE    = "#60a5fa"  # blue - int, string
    COLOR_STRING  = "#fbbf24"  # amber - 'quoted values'
    COLOR_NUMBER  = "#f87171"  # red - numeric literals
    COLOR_COMMENT = "#555555"  # grey - -- comments

    KEYWORDS = [
        "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES",
        "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "DROP",
        "INDEX", "ON", "PRIMARY", "KEY", "UNIQUE", "ORDER", "BY",
        "ASC", "DESC", "LIMIT", "AND", "OR", "NOT", "NULL",
        "BEGIN", "COMMIT", "ROLLBACK", "IN", "IS", "LIKE",
        "BETWEEN", "REFERENCES", "FOREIGN",
    ]

    TYPES = ["INT", "STRING", "FLOAT", "BOOL"]

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
        # SQL keywords - whole word match, case insensitive
        keyword_fmt = self._fmt(self.COLOR_KEYWORD, bold=True)
        for kw in self.KEYWORDS:
            self.rules.append((
                re.compile(rf"\b{kw}\b", re.IGNORECASE),
                keyword_fmt
            ))

        # Data types
        type_fmt = self._fmt(self.COLOR_TYPE)
        for t in self.TYPES:
            self.rules.append((
                re.compile(rf"\b{t}\b", re.IGNORECASE),
                type_fmt
            ))

        # Single-quoted strings: 'value'
        self.rules.append((
            re.compile(r"'[^']*'"),
            self._fmt(self.COLOR_STRING)
        ))

        # Numeric literals
        self.rules.append((
            re.compile(r"\b\d+(\.\d+)?\b"),
            self._fmt(self.COLOR_NUMBER)
        ))

        # Single-line comments: -- comment
        self.rules.append((
            re.compile(r"--[^\n]*"),
            self._fmt(self.COLOR_COMMENT)
        ))

    def highlightBlock(self, text: str):
        """
        Called by Qt automatically for each line of text.
        Applies all rules in order - later rules override earlier ones.
        """
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(
                    match.start(),
                    match.end() - match.start(),
                    fmt
                )