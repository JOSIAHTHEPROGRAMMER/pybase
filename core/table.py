from storage.pager import Pager
from storage.schema_manager import SchemaManager
from storage.index_manager import IndexManager
from query.expression import Expression

class Table:
    SUPPORTED_TYPES = {"int": int, "string": str}

    def __init__(self, name: str, columns: list[tuple[str, str]],
                 unique_columns: set = None, folder: str = "data"):
        self.name = name
        self.columns = columns
        self.folder = folder
        self.schema_manager = SchemaManager(name, folder)
        self.pager = Pager(name, columns, folder)
        self._validate_schema()
        self.rows = self.pager.load_all_rows()
        self.index_manager = IndexManager()

        if unique_columns is not None:
            # Fresh table creation
            self.unique_columns = unique_columns
            self.primary_key = None
            self.foreign_keys = []
            self.schema_manager.write(
                self.columns, self.unique_columns,
                self.primary_key, [], self.foreign_keys
            )
        else:
            # Reopening existing table
            schema = self.schema_manager.read()
            self.unique_columns = set(schema.get("unique_columns", []))
            self.primary_key = schema.get("primary_key", None)
            self.foreign_keys = schema.get("foreign_keys", [])

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

    def _persist_schema(self):
        """
        Write the current full schema state to disk.
        Called after any constraint or index change.
        Centralizes all schema writes through one method.
        """
        schema = self.schema_manager.read()
        self.schema_manager.write(
            self.columns,
            self.unique_columns,
            self.primary_key,
            schema.get("indexes", []),
            self.foreign_keys
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

        self.unique_columns.add(column_name)
        self.primary_key = column_name
        self._persist_schema()

    def add_unique_constraint(self, column_name: str):
        """
        Add a UNIQUE constraint to an existing column.
        Persists updated schema to disk immediately.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        self.unique_columns.add(column_name)
        self._persist_schema()

    def add_foreign_key(self, column_name: str, ref_table: str, ref_column: str):
        """
        Register a foreign key constraint on a column.

        column_name: column in this table that holds the FK value
        ref_table:   name of the referenced table
        ref_column:  column in the referenced table being pointed to

        The referenced table and column are validated to exist.
        Persists the FK definition to schema immediately.
        """
        col_names = [col[0] for col in self.columns]
        if column_name not in col_names:
            raise ValueError(f"Column '{column_name}' does not exist.")

        fk = {
            "column":     column_name,
            "ref_table":  ref_table,
            "ref_column": ref_column
        }

        self.foreign_keys.append(fk)
        self._persist_schema()

    def _build_column_index(self) -> dict:
        """
        Build a name to position map for the current schema.
        Used by insert, select, delete, update to avoid repeated enumeration.
        """
        return {name: i for i, (name, _) in enumerate(self.columns)}

    def _matches_conditions(self, row: list, conditions: list,
                            column_index: dict) -> bool:
        """
        Evaluate all conditions against a row using the Expression evaluator.
        All conditions in the list must be satisfied (AND logic at the top level).
        OR logic is handled inside individual condition dicts.
        """
        for condition in conditions:
            if not Expression.evaluate(condition, row, column_index):
                return False
        return True

    def _validate_foreign_keys(self, row: list, db):
        """
        Check that all FK values in a row exist in their referenced tables.
        Called on insert and update before writing anything.
        Raises ValueError if a referenced value does not exist.
        db is passed in so we can look up other tables.
        """
        if not self.foreign_keys or db is None:
            return

        column_index = self._build_column_index()

        for fk in self.foreign_keys:
            col      = fk["column"]
            ref_name = fk["ref_table"]
            ref_col  = fk["ref_column"]

            if col not in column_index:
                continue

            value = row[column_index[col]]

            if ref_name not in db.tables:
                raise ValueError(
                    f"Referenced table '{ref_name}' does not exist."
                )

            ref_table = db.tables[ref_name]
            ref_col_index = ref_table._build_column_index()

            if ref_col not in ref_col_index:
                raise ValueError(
                    f"Referenced column '{ref_col}' does not exist "
                    f"in table '{ref_name}'."
                )

            ref_idx = ref_col_index[ref_col]
            exists = any(
                existing_row[ref_idx] == value
                for existing_row in ref_table.rows
            )

            if not exists:
                raise ValueError(
                    f"Foreign key violation: '{col}' value {value!r} "
                    f"does not exist in '{ref_name}.{ref_col}'."
                )

    def create_index(self, column_name: str):
        """
        Build a B-Tree index on a column.
        Populates index from existing rows then persists to schema.
        Future inserts, deletes, and updates maintain the index automatically.
        Returns a message string so the caller decides whether to print it.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        column_index = self._build_column_index()
        col_idx = column_index[column_name]

        self.index_manager.create_index(column_name)
        self.index_manager.rebuild(column_name, self.rows, col_idx)

        schema = self.schema_manager.read()
        indexes = schema.get("indexes", [])

        if column_name not in indexes:
            indexes.append(column_name)

        self.schema_manager.write(
            self.columns,
            self.unique_columns,
            self.primary_key,
            indexes,
            self.foreign_keys
        )

        return f"Index created on '{column_name}'."

    def insert(self, row: list, db=None):
        """
        Validate and insert a new row into the table.
        Enforces: column count, types, NOT NULL on PK, no duplicates,
        UNIQUE constraints, and foreign key constraints.
        Appends to in-memory rows and persists to disk via pager.
        Maintains all active B-Tree indexes after successful insert.
        db is optional and only needed for FK validation.
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

        if self.primary_key is not None:
            pk_index = next(
                i for i, (name, _) in enumerate(self.columns)
                if name == self.primary_key
            )
            if row[pk_index] is None:
                raise ValueError(
                    f"PRIMARY KEY column '{self.primary_key}' cannot be NULL."
                )

        if row in self.rows:
            raise ValueError("Duplicate row insertion is not allowed.")

        column_index = self._build_column_index()

        for unique_col in self.unique_columns:
            idx = column_index[unique_col]
            for existing_row in self.rows:
                if existing_row[idx] == row[idx]:
                    raise ValueError(
                        f"Duplicate value for UNIQUE column '{unique_col}'."
                    )

        # Validate FK constraints if a db reference is provided
        self._validate_foreign_keys(row, db)

        self.rows.append(row)
        self.pager.append_row(row)

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
        Kept for backwards compatibility, select_advanced is preferred.
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
        LIMIT is applied last after filtering, ordering, and projection.
        """
        if selected_columns != ["*"]:
            for col in selected_columns:
                if col not in [c[0] for c in self.columns]:
                    raise ValueError(f"Column '{col}' does not exist.")

        column_index = self._build_column_index()

        for condition in conditions:
            if condition.get("type") == "simple":
                if condition["column"] not in column_index:
                    raise ValueError(f"Column '{condition['column']}' does not exist.")
            
            
        if order_by is not None:
            order_col, order_dir = order_by
            if order_col not in column_index:
                raise ValueError(f"Column '{order_col}' does not exist.")
            if order_dir.upper() not in ("ASC", "DESC"):
                raise ValueError("ORDER BY direction must be ASC or DESC.")

        if limit is not None and (not isinstance(limit, int) or limit < 1):
            raise ValueError("LIMIT must be a positive integer.")

        if (
            len(conditions) == 1
            and conditions[0].get("type") == "simple"
            and conditions[0].get("op") == "="
            and self.index_manager.has_index(conditions[0].get("column"))
        ):
            col = conditions[0]["column"]
            val = conditions[0]["value"]
            filtered_rows = self.index_manager.search(col, val) or []
        else:
            filtered_rows = [
                row for row in self.rows
                if self._matches_conditions(row, conditions, column_index)
            ]

        if order_by is not None:
            order_col, order_dir = order_by
            col_idx = column_index[order_col]
            reverse = order_dir.upper() == "DESC"
            filtered_rows = sorted(
                filtered_rows,
                key=lambda row: row[col_idx],
                reverse=reverse
            )

        if limit is not None:
            filtered_rows = filtered_rows[:limit]

        if selected_columns == ["*"]:
            return filtered_rows

        return [
            [row[column_index[col]] for col in selected_columns]
            for row in filtered_rows
        ]

    def delete(self, conditions: list):
        """
        Delete all rows matching ALL conditions.
        Requires at least one WHERE condition, full table deletes not yet supported.
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

        for condition in conditions:
            if condition.get("type") == "simple":
                if condition["column"] not in column_index:
                    raise ValueError(f"Column '{condition['column']}' does not exist.")
            
            
            
        surviving_rows = []
        deleted_count = 0

        for row in self.rows:
            if self._matches_conditions(row, conditions, column_index):
                deleted_count += 1
            else:
                surviving_rows.append(row)

        if deleted_count > 0:
            self.rows = surviving_rows
            self.pager.rewrite_all_rows(surviving_rows)

            for col in self.index_manager.indexes:
                self.index_manager.rebuild(col, self.rows, column_index[col])

        return deleted_count

    def update(self, assignments: list, conditions: list, db=None):
        """
        Update specific columns in rows matching ALL conditions.
        Requires at least one WHERE condition, full table updates not yet supported.

        assignments: list of (column, value) columns to change
        conditions:  list of (column, operator, value) rows to target
        db:          optional database reference for FK validation

        Enforces types, UNIQUE constraints, NOT NULL on PK, and FK constraints.
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

        for col, value in assignments:
            if col not in column_index:
                raise ValueError(f"Column '{col}' does not exist.")

            expected_type = self.SUPPORTED_TYPES[column_types[col]]
            if not isinstance(value, expected_type):
                raise TypeError(
                    f"Column '{col}' expects type '{column_types[col]}', "
                    f"but got '{type(value).__name__}'."
                )

            if col == self.primary_key and value is None:
                raise ValueError(
                    f"PRIMARY KEY column '{self.primary_key}' cannot be set to NULL."
                )

        for condition in conditions:
            if condition.get("type") == "simple":
                if condition["column"] not in column_index:
                    raise ValueError(f"Column '{condition['column']}' does not exist.")
            
     
        updated_count = 0
        updated_rows = []

        for row in self.rows:
            if self._matches_conditions(row, conditions, column_index):
                new_row = list(row)

                for col, value in assignments:
                    if col in self.unique_columns:
                        idx = column_index[col]
                        for existing_row in self.rows:
                            if existing_row[idx] == value and existing_row != row:
                                raise ValueError(
                                    f"Duplicate value for UNIQUE column '{col}'."
                                )

                    new_row[column_index[col]] = value

                # Validate FK constraints on the updated row
                self._validate_foreign_keys(new_row, db)

                updated_rows.append(new_row)
                updated_count += 1
            else:
                updated_rows.append(row)

        if updated_count > 0:
            self.rows = updated_rows
            self.pager.rewrite_all_rows(updated_rows)

            for col in self.index_manager.indexes:
                self.index_manager.rebuild(col, self.rows, column_index[col])

        return updated_count