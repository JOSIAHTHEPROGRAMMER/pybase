class Table:
    SUPPORTED_TYPES = {"int": int, "string": str}

    def __init__(self, name: str, columns: list[tuple[str, str]]):
        """
        Initialize a table with a name and schema.

        columns format:
        [
            ("id", "int"),
            ("name", "string")
        ]
        """
        self.name = name
        self.columns = columns
        self.rows = []

        self._validate_schema()

    def _validate_schema(self):
        """
        Ensure column types are supported.
        """
        for column_name, column_type in self.columns:
            if column_type not in self.SUPPORTED_TYPES:
                raise ValueError(
                    f"Unsupported column type '{column_type}' "
                    f"for column '{column_name}'."
                )

    def insert(self, row: list):
        """
        Insert a row into the table with strict type checking.
        """
        if len(row) != len(self.columns):
            raise ValueError(
                f"Expected {len(self.columns)} values, got {len(row)}."
            )

        for value, (column_name, column_type) in zip(row, self.columns):
            expected_python_type = self.SUPPORTED_TYPES[column_type]

            if not isinstance(value, expected_python_type):
                raise TypeError(
                    f"Column '{column_name}' expects type '{column_type}', "
                    f"but got '{type(value).__name__}'."
                )

        self.rows.append(row)

    def select_all(self):
        """
        Return all rows.
        """
        return self.rows