from storage.pager import Pager
from storage.schema_manager import SchemaManager
from storage.index_manager import IndexManager


class Table:
    SUPPORTED_TYPES = {"int": int, "string": str}

    def __init__(self, name: str, columns: list[tuple[str, str]], unique_columns: set = None):
        self.name = name
        self.columns = columns
        self.schema_manager = SchemaManager(name)
        self.pager = Pager(name, columns)
        self._validate_schema()
        self.rows = self.pager.load_all_rows()
        self.index_manager = IndexManager()

        if unique_columns is not None:
            # Fresh table creation — initialize constraints and persist schema
            self.unique_columns = unique_columns
            self.primary_key = None
            self.schema_manager.write(self.columns, self.unique_columns, self.primary_key)
        else:
            # Reopening existing table — restore constraints and rebuild indexes from disk
            schema = self.schema_manager.read()
            self.unique_columns = set(schema.get("unique_columns", []))
            self.primary_key = schema.get("primary_key", None)

            # Rebuild in-memory indexes from persisted index list in schema
            column_index = self._build_column_index()
            for col in schema.get("indexes", []):
                if col in column_index:
                    self.index_manager.create_index(col)
                    self.index_manager.rebuild(col, self.rows, column_index[col])

    def _validate_schema(self):
        """
        Ensure all column types are supported before any operations.
        Fails fast at table creation rather than at insert time.
        """
        for column_name, column_type in self.columns:
            if column_type not in self.SUPPORTED_TYPES:
                raise ValueError(
                    f"Unsupported column type '{column_type}' "
                    f"for column '{column_name}'."
                )

    def set_primary_key(self, column_name: str):
        """
        Designate a column as PRIMARY KEY.
        PRIMARY KEY = UNIQUE + NOT NULL. Only one allowed per table.
        Persists updated schema to disk immediately.
        """
        if self.primary_key is not None:
            raise ValueError(
                f"Table '{self.name}' already has a primary key: '{self.primary_key}'."
            )

        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        # PRIMARY KEY implies UNIQUE — add to constraint set
        self.unique_columns.add(column_name)
        self.primary_key = column_name

        self.schema_manager.write(self.columns, self.unique_columns, self.primary_key)

    def add_unique_constraint(self, column_name: str):
        """
        Add a UNIQUE constraint to an existing column.
        Persists updated schema to disk immediately.
        primary_key is passed through to avoid wiping it from the schema.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        self.unique_columns.add(column_name)

        # Always pass primary_key to avoid overwriting it with None
        self.schema_manager.write(self.columns, self.unique_columns, self.primary_key)

    def _build_column_index(self) -> dict:
        """
        Build a name -> position map for the current schema.
        Used by insert, select, delete, update to avoid repeated enumeration.
        """
        return {name: i for i, (name, _) in enumerate(self.columns)}

    def _matches_conditions(self, row: list, conditions: list, column_index: dict) -> bool:
        """
        Return True if a row satisfies ALL conditions (AND logic).
        Central predicate evaluator — single place to extend operators.

        Supported operators: =, !=, >, >=, <, <=
        """
        for column, operator, value in conditions:
            cell_value = row[column_index[column]]

            if operator == "=" and not (cell_value == value):
                return False
            elif operator == "!=" and not (cell_value != value):
                return False
            elif operator == ">=" and not (cell_value >= value):
                return False
            elif operator == "<=" and not (cell_value <= value):
                return False
            elif operator == ">" and not (cell_value > value):
                return False
            elif operator == "<" and not (cell_value < value):
                return False

        return True

    def create_index(self, column_name: str):
        """
        Build a B-Tree index on a column.
        Populates index from existing rows, then persists to schema.
        Future inserts/deletes/updates maintain the index automatically.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        column_index = self._build_column_index()
        col_idx = column_index[column_name]

        # Build index from all current rows
        self.index_manager.create_index(column_name)
        self.index_manager.rebuild(column_name, self.rows, col_idx)

        # Persist index list to schema so it survives restart
        schema = self.schema_manager.read()
        indexes = schema.get("indexes", [])

        if column_name not in indexes:
            indexes.append(column_name)

        self.schema_manager.write(
            self.columns,
            self.unique_columns,
            self.primary_key,
            indexes
        )

        print(f"Index created on '{column_name}'.")

    def insert(self, row: list):
        """
        Validate and insert a new row into the table.
        Enforces: column count, types, NOT NULL on PK, no duplicates, UNIQUE constraints.
        Appends to in-memory rows and persists to disk via pager.
        Maintains all active B-Tree indexes after successful insert.
        """
        if len(row) != len(self.columns):
            raise ValueError(
                f"Expected {len(self.columns)} values, got {len(row)}."
            )

        # Strict type checking against schema
        for value, (column_name, column_type) in zip(row, self.columns):
            expected_python_type = self.SUPPORTED_TYPES[column_type]
            if not isinstance(value, expected_python_type):
                raise TypeError(
                    f"Column '{column_name}' expects type '{column_type}', "
                    f"but got '{type(value).__name__}'."
                )

        # NOT NULL enforcement for primary key column
        if self.primary_key is not None:
            pk_index = next(
                i for i, (name, _) in enumerate(self.columns)
                if name == self.primary_key
            )
            if row[pk_index] is None:
                raise ValueError(
                    f"PRIMARY KEY column '{self.primary_key}' cannot be NULL."
                )

        # Reject exact duplicate rows entirely
        if row in self.rows:
            raise ValueError("Duplicate row insertion is not allowed.")

        # Enforce UNIQUE constraints across all flagged columns
        column_index = self._build_column_index()

        for unique_col in self.unique_columns:
            idx = column_index[unique_col]
            for existing_row in self.rows:
                if existing_row[idx] == row[idx]:
                    raise ValueError(
                        f"Duplicate value for UNIQUE column '{unique_col}'."
                    )

        self.rows.append(row)
        self.pager.append_row(row)

        # Keep all active B-Tree indexes up to date on every insert
        for col in self.index_manager.indexes:
            self.index_manager.index_row(col, row[column_index[col]], row)

    def select_all(self):
        """
        Reload all rows fresh from disk and return them.
        Useful for debugging or verifying persistence directly.
        """
        self.rows = self.pager.load_all_rows()
        return self.rows

    def select_where(self, column_name: str, value):
        """
        Simple equality filter on a single column.
        Kept for backwards compatibility — select_advanced is preferred.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        column_index = next(
            i for i, (name, _) in enumerate(self.columns)
            if name == column_name
        )

        return [row for row in self.rows if row[column_index] == value]

    def select_advanced(self, selected_columns: list, conditions: list,
                        order_by: tuple = None, limit: int = None):
        """
        Full SELECT with column projection, WHERE filtering, ORDER BY, and LIMIT.

        selected_columns: ["*"] for all, or list of column name strings
        conditions:       list of (column, operator, value) tuples
        order_by:         (column_name, direction) e.g. ("id", "ASC") or None
        limit:            max number of rows to return, or None for all

        Uses B-Tree index for single equality conditions on indexed columns.
        Falls back to full table scan for range queries or non-indexed columns.
        LIMIT is applied last — after filtering, ordering, and projection.
        """
        if selected_columns != ["*"]:
            for col in selected_columns:
                if col not in [c[0] for c in self.columns]:
                    raise ValueError(f"Column '{col}' does not exist.")

        column_index = self._build_column_index()

        # Validate condition columns exist before filtering
        for column, _, _ in conditions:
            if column not in column_index:
                raise ValueError(f"Column '{column}' does not exist.")

        # Validate ORDER BY column and direction
        if order_by is not None:
            order_col, order_dir = order_by
            if order_col not in column_index:
                raise ValueError(f"Column '{order_col}' does not exist.")
            if order_dir.upper() not in ("ASC", "DESC"):
                raise ValueError("ORDER BY direction must be ASC or DESC.")

        # Validate LIMIT is a positive integer
        if limit is not None and (not isinstance(limit, int) or limit < 1):
            raise ValueError("LIMIT must be a positive integer.")

        # Use B-Tree index for single equality condition on indexed column
        if (
            len(conditions) == 1
            and conditions[0][1] == "="
            and self.index_manager.has_index(conditions[0][0])
        ):
            col, _, val = conditions[0]
            filtered_rows = self.index_manager.search(col, val) or []
        else:
            # Fall back to full table scan
            filtered_rows = [
                row for row in self.rows
                if self._matches_conditions(row, conditions, column_index)
            ]

        # Apply ORDER BY — sort filtered rows before limiting
        if order_by is not None:
            order_col, order_dir = order_by
            col_idx = column_index[order_col]
            reverse = order_dir.upper() == "DESC"
            filtered_rows = sorted(
                filtered_rows,
                key=lambda row: row[col_idx],
                reverse=reverse
            )

        # Apply LIMIT — slice after filtering and ordering
        if limit is not None:
            filtered_rows = filtered_rows[:limit]

        # Return all columns if wildcard, otherwise project requested columns
        if selected_columns == ["*"]:
            return filtered_rows

        return [
            [row[column_index[col]] for col in selected_columns]
            for row in filtered_rows
        ]

    def delete(self, conditions: list):
        """
        Delete all rows matching ALL conditions.
        Requires at least one WHERE condition — full table deletes not yet supported.
        Rewrites the .db file after deletion via pager.
        Rebuilds all active B-Tree indexes after rewrite.

        Returns the number of rows deleted.
        """
        if not conditions:
            raise ValueError(
                "DELETE requires at least one WHERE condition. "
                "Full table deletes are not supported yet."
            )

        column_index = self._build_column_index()

        # Validate all condition columns exist before touching any rows
        for column, _, _ in conditions:
            if column not in column_index:
                raise ValueError(f"Column '{column}' does not exist.")

        surviving_rows = []
        deleted_count = 0

        for row in self.rows:
            if self._matches_conditions(row, conditions, column_index):
                deleted_count += 1
            else:
                surviving_rows.append(row)

        # Only rewrite disk if rows were actually removed
        if deleted_count > 0:
            self.rows = surviving_rows
            self.pager.rewrite_all_rows(surviving_rows)

            # Rebuild all indexes against the new row set after bulk rewrite
            for col in self.index_manager.indexes:
                self.index_manager.rebuild(col, self.rows, column_index[col])

        return deleted_count

    def update(self, assignments: list, conditions: list):
        """
        Update specific columns in rows matching ALL conditions.
        Requires at least one WHERE condition — full table updates not yet supported.

        assignments: list of (column, value) — columns to change
        conditions:  list of (column, operator, value) — rows to target

        Enforces types, UNIQUE constraints, and NOT NULL on primary key.
        Rewrites the .db file after updates via pager.
        Rebuilds all active B-Tree indexes after rewrite.

        Returns the number of rows updated.
        """
        if not conditions:
            raise ValueError(
                "UPDATE requires at least one WHERE condition. "
                "Full table updates are not supported yet."
            )

        column_index = self._build_column_index()
        column_types = {name: ctype for name, ctype in self.columns}

        # Validate all assignments up front before mutating anything
        for col, value in assignments:
            if col not in column_index:
                raise ValueError(f"Column '{col}' does not exist.")

            expected_type = self.SUPPORTED_TYPES[column_types[col]]
            if not isinstance(value, expected_type):
                raise TypeError(
                    f"Column '{col}' expects type '{column_types[col]}', "
                    f"but got '{type(value).__name__}'."
                )

            # Block attempts to set primary key column to NULL
            if col == self.primary_key and value is None:
                raise ValueError(
                    f"PRIMARY KEY column '{self.primary_key}' cannot be set to NULL."
                )

        # Validate all condition columns exist
        for col, _, _ in conditions:
            if col not in column_index:
                raise ValueError(f"Column '{col}' does not exist.")

        updated_count = 0
        updated_rows = []

        for row in self.rows:
            if self._matches_conditions(row, conditions, column_index):
                new_row = list(row)

                for col, value in assignments:
                    # Enforce UNIQUE — check no other existing row has this value
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

        # Only rewrite disk if rows were actually changed
        if updated_count > 0:
            self.rows = updated_rows
            self.pager.rewrite_all_rows(updated_rows)

            # Rebuild all indexes against the updated row set after bulk rewrite
            for col in self.index_manager.indexes:
                self.index_manager.rebuild(col, self.rows, column_index[col])

        return updated_count