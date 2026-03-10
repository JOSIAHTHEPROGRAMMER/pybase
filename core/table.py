from storage.pager import Pager
from storage.schema_manager import SchemaManager


class Table:
    SUPPORTED_TYPES = {"int": int, "string": str}

    def __init__(self, name: str, columns: list[tuple[str, str]], unique_columns: set = None):
        """
        Initialize a table. If unique_columns is provided, this is a
        fresh creation — persist schema. Otherwise, schema was already written.
        """
        self.name = name
        self.columns = columns
        self.schema_manager = SchemaManager(name)
        self.pager = Pager(name, columns)
        self._validate_schema()
        self.rows = self.pager.load_all_rows()

        # Restore or initialize unique constraints
        if unique_columns is not None:
            # Fresh table creation — persist schema now
            self.unique_columns = unique_columns
            self.schema_manager.write(self.columns, self.unique_columns)
        else:
            # Reopening existing table — load constraints from disk
            schema = self.schema_manager.read()
            self.unique_columns = set(schema.get("unique_columns", []))

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
        
        # Auto-persist schema whenever constraints change
        self.schema_manager.write(self.columns, self.unique_columns)


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
    

    def delete(self, conditions: list):
        """
        Delete all rows matching ALL conditions (AND logic).
        conditions: list of (column, operator, value) tuples

        Returns the number of rows deleted.
        """
        if not conditions:
            raise ValueError(
                "DELETE requires at least one WHERE condition. "
                "Full table deletes are not supported yet."
            )

        column_index = {name: i for i, (name, _) in enumerate(self.columns)}

        # Validate condition columns exist
        for column, _, _ in conditions:
            if column not in column_index:
                raise ValueError(f"Column '{column}' does not exist.")

        surviving_rows = []
        deleted_count = 0

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
                deleted_count += 1
            else:
                surviving_rows.append(row)

        # Only touch disk if something actually changed
        if deleted_count > 0:
            self.rows = surviving_rows
            self.pager.rewrite_all_rows(surviving_rows)

        return deleted_count
    
    def update(self, assignments: list, conditions: list):
        """
        Update columns in rows matching all conditions.

        assignments: list of (column, value) tuples — what to change
        conditions:  list of (column, operator, value) tuples — which rows

        Returns the number of rows updated.
        """
        if not conditions:
            raise ValueError(
                "UPDATE requires at least one WHERE condition. "
                "Full table updates are not supported yet."
            )

        column_index = {name: i for i, (name, _) in enumerate(self.columns)}
        column_types = {name: ctype for name, ctype in self.columns}

        # Validate assignment columns and types up front
        for col, value in assignments:
            if col not in column_index:
                raise ValueError(f"Column '{col}' does not exist.")

            expected_type = self.SUPPORTED_TYPES[column_types[col]]
            if not isinstance(value, expected_type):
                raise TypeError(
                    f"Column '{col}' expects type '{column_types[col]}', "
                    f"but got '{type(value).__name__}'."
                )

        # Validate condition columns exist
        for col, _, _ in conditions:
            if col not in column_index:
                raise ValueError(f"Column '{col}' does not exist.")

        updated_count = 0
        updated_rows = []

        for row in self.rows:
            # Check if this row matches all conditions
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
                # Apply assignments to a copy of the row
                new_row = list(row)

                for col, value in assignments:
                    # Enforce UNIQUE constraints on updated value
                    if col in self.unique_columns:
                        idx = column_index[col]
                        for existing_row in self.rows:
                            if existing_row[idx] == value and existing_row != row:
                                raise ValueError(
                                    f"Duplicate value for UNIQUE column '{col}'."
                                )

                    new_row[column_index[col]] = value

                updated_rows.append(new_row)
                updated_count += 1
            else:
                updated_rows.append(row)

        # Only touch disk if something actually changed
        if updated_count > 0:
            self.rows = updated_rows
            self.pager.rewrite_all_rows(updated_rows)

        return updated_count