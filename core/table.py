from ..storage.pager import Pager

class Table:
    SUPPORTED_TYPES = {"int": int, "string": str}

    def __init__(self, name: str, columns: list[tuple[str, str]]):
        """
        Initialize a table with a name, schema, and persistent storage.
        """
        self.name = name
        self.columns = columns
        self.pager = Pager(name, columns)  # handle disk persistence
        self._validate_schema()
        self.rows = self.pager.load_all_rows()  # load persisted rows
        self.unique_columns = set()

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
            
    def add_unique_constraint(self, column_name: str):
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        self.unique_columns.add(column_name)

    def insert(self, row: list):
        if len(row) != len(self.columns):
            raise ValueError(
                f"Expected {len(self.columns)} values, got {len(row)}."
            )

        # Strict type checking
        for value, (column_name, column_type) in zip(row, self.columns):
            expected_python_type = self.SUPPORTED_TYPES[column_type]

            if not isinstance(value, expected_python_type):
                raise TypeError(
                    f"Column '{column_name}' expects type '{column_type}', "
                    f"but got '{type(value).__name__}'."
                )

        # Prevent exact duplicate rows
        if row in self.rows:
            raise ValueError("Duplicate row insertion is not allowed.")

        # Enforce UNIQUE constraints
        column_index = {name: i for i, (name, _) in enumerate(self.columns)}

        for unique_col in self.unique_columns:
            idx = column_index[unique_col]

            for existing_row in self.rows:
                if existing_row[idx] == row[idx]:
                    raise ValueError(
                        f"Duplicate value for UNIQUE column '{unique_col}'."
                    )

        self.rows.append(row)
        self.pager.append_row(row)
        
    def select_all(self):
        """
        Reload persisted rows and return them.
        """
        self.rows = self.pager.load_all_rows()
        return self.rows
    
    def select_where(self, column_name: str, value):
        """
        Return rows where column_name == value.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        column_index = next(
            i for i, (name, _) in enumerate(self.columns)
            if name == column_name
        )

        filtered_rows = [
            row for row in self.rows
            if row[column_index] == value
        ]

        return filtered_rows
    
    def select_advanced(self, selected_columns, conditions):
        """
        selected_columns: list[str] or ["*"]
        conditions: list of tuples -> [(column, operator, value), ...]

        Example:
            selected_columns = ["name"]
            conditions = [("id", ">", 1), ("name", "=", "Josh")]
        """

        # Validate selected columns
        if selected_columns != ["*"]:
            for col in selected_columns:
                if col not in [c[0] for c in self.columns]:
                    raise ValueError(f"Column '{col}' does not exist.")

        # Build column index map
        column_index = {name: i for i, (name, _) in enumerate(self.columns)}

        # Filter rows
        filtered_rows = []

        for row in self.rows:
            match = True

            for column, operator, value in conditions:
                idx = column_index[column]
                cell_value = row[idx]

                if operator == "=" and not (cell_value == value):
                    match = False
                elif operator == ">" and not (cell_value > value):
                    match = False
                elif operator == "<" and not (cell_value < value):
                    match = False

            if match:
                filtered_rows.append(row)

        # Handle column projection
        if selected_columns == ["*"]:
            return filtered_rows

        projected_rows = []
        for row in filtered_rows:
            projected_rows.append(
                [row[column_index[col]] for col in selected_columns]
            )

        return projected_rows