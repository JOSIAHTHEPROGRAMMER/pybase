from storage.pager import Pager
from storage.schema_manager import SchemaManager
from storage.index_manager import IndexManager
from query.expression import Expression


class Table:
    SUPPORTED_TYPES = {
        "int":     int,
        "bigint":  int,
        "float":   float,
        "boolean": bool,
        "string":  str
    }

    def __init__(self, name: str, columns: list[tuple[str, str]],
                 unique_columns: set = None, folder: str = "data"):
        self.name    = name
        self.columns = columns
        self.folder  = folder
        self.schema_manager = SchemaManager(name, folder)
        self.pager          = Pager(name, columns, folder)
        self._validate_schema()
        self.rows          = self.pager.load_all_rows()
        self.index_manager = IndexManager()

        if unique_columns is not None:
            # Fresh table creation
            self.unique_columns      = unique_columns
            self.primary_key         = None
            self.composite_primary_key = []
            self.foreign_keys        = []
            self.not_null_columns    = set()
            self.default_values      = {}
            self.check_constraints   = []
            self.composite_unique    = []
            self.auto_increment      = None
            self._persist_schema()
        else:
            # Reopening existing table
            schema = self.schema_manager.read()
            self.unique_columns        = set(schema.get("unique_columns", []))
            self.primary_key           = schema.get("primary_key", None)
            self.composite_primary_key = schema.get("composite_primary_key", [])
            self.foreign_keys          = schema.get("foreign_keys", [])
            self.not_null_columns      = set(schema.get("not_null_columns", []))
            self.default_values        = schema.get("default_values", {})
            self.check_constraints     = schema.get("check_constraints", [])
            self.composite_unique      = schema.get("composite_unique", [])
            self.auto_increment        = schema.get("auto_increment", None)

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
        Called after any constraint or metadata change.
        Centralizes all schema writes through one method.
        """
        schema = self.schema_manager.read() if self.schema_manager.exists() else {}
        self.schema_manager.write(
            self.columns,
            self.unique_columns,
            self.primary_key,
            schema.get("indexes", []),
            self.foreign_keys,
            list(self.not_null_columns),
            self.default_values,
            self.check_constraints,
            self.auto_increment,
            self.composite_primary_key,
            self.composite_unique
        )

    def set_primary_key(self, column_name: str):
        """
        Designate a single column as PRIMARY KEY.
        PRIMARY KEY = UNIQUE + NOT NULL. Only one allowed per table.
        Use set_composite_primary_key for multi-column primary keys.
        Persists updated schema to disk immediately.
        """
        if self.primary_key is not None or self.composite_primary_key:
            raise ValueError(
                f"Table '{self.name}' already has a primary key."
            )

        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        self.unique_columns.add(column_name)
        self.not_null_columns.add(column_name)
        self.primary_key = column_name
        self._persist_schema()

    def set_composite_primary_key(self, column_names: list):
        """
        Designate multiple columns together as a composite PRIMARY KEY.
        All columns in the composite key are implicitly NOT NULL.
        The combination of values must be unique across all rows.
        Persists updated schema to disk immediately.
        """
        if self.primary_key is not None or self.composite_primary_key:
            raise ValueError(
                f"Table '{self.name}' already has a primary key."
            )

        col_names = [col[0] for col in self.columns]
        for col in column_names:
            if col not in col_names:
                raise ValueError(f"Column '{col}' does not exist.")
            self.not_null_columns.add(col)

        self.composite_primary_key = column_names
        self._persist_schema()

    def add_unique_constraint(self, column_name: str):
        """
        Add a single-column UNIQUE constraint.
        Persists updated schema to disk immediately.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        self.unique_columns.add(column_name)
        self._persist_schema()

    def add_composite_unique(self, column_names: list):
        """
        Add a composite UNIQUE constraint spanning multiple columns.
        The combination of values across those columns must be unique.
        Persists updated schema to disk immediately.
        """
        col_names = [col[0] for col in self.columns]
        for col in column_names:
            if col not in col_names:
                raise ValueError(f"Column '{col}' does not exist.")

        self.composite_unique.append(column_names)
        self._persist_schema()

    def add_not_null_constraint(self, column_name: str):
        """
        Mark a column as NOT NULL.
        Raises if any existing row has NULL in that column.
        Persists updated schema to disk immediately.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        col_idx = self._build_column_index()[column_name]
        for row in self.rows:
            if row[col_idx] is None:
                raise ValueError(
                    f"Cannot add NOT NULL to '{column_name}': "
                    f"existing rows contain NULL values."
                )

        self.not_null_columns.add(column_name)
        self._persist_schema()

    def set_default_value(self, column_name: str, value):
        """
        Set a default value for a column.
        Used when INSERT omits that column or passes NULL.
        Persists updated schema to disk immediately.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        self.default_values[column_name] = value
        self._persist_schema()

    def add_check_constraint(self, column_name: str, op: str, value):
        """
        Add a CHECK constraint to a column.
        Evaluated on every insert and update.
        Persists updated schema to disk immediately.
        """
        if column_name not in [col[0] for col in self.columns]:
            raise ValueError(f"Column '{column_name}' does not exist.")

        constraint = {"column": column_name, "op": op, "value": value}
        self.check_constraints.append(constraint)
        self._persist_schema()

    def set_auto_increment(self, column_name: str, start: int = 1):
        """
        Enable AUTO_INCREMENT on an int or bigint PRIMARY KEY column.
        Counter is persisted to schema so values are never reused after restart.
        Persists updated schema to disk immediately.
        """
        col_names = [col[0] for col in self.columns]
        col_types = {name: ctype for name, ctype in self.columns}

        if column_name not in col_names:
            raise ValueError(f"Column '{column_name}' does not exist.")

        if col_types[column_name] not in ("int", "bigint"):
            raise ValueError(
                f"AUTO_INCREMENT only supported on int or bigint columns, "
                f"got '{col_types[column_name]}'."
            )

        if column_name != self.primary_key:
            raise ValueError(
                "AUTO_INCREMENT only supported on PRIMARY KEY columns."
            )

        if self.rows:
            col_idx  = self._build_column_index()[column_name]
            max_val  = max(row[col_idx] for row in self.rows)
            next_val = max(start, max_val + 1)
        else:
            next_val = start

        self.auto_increment = {"column": column_name, "next_value": next_val}
        self._persist_schema()

    def _get_next_auto_increment(self) -> int:
        """
        Return the next AUTO_INCREMENT value and advance the counter.
        Persists the updated counter immediately so it survives restarts.
        """
        val = self.auto_increment["next_value"]
        self.auto_increment["next_value"] = val + 1
        self._persist_schema()
        return val

    def add_foreign_key(self, column_name: str, ref_table: str,
                        ref_column: str, on_delete: str = None,
                        on_update: str = None):
        """
        Register a foreign key constraint on a column.

        column_name: column in this table holding the FK value
        ref_table:   name of the referenced table
        ref_column:  column in the referenced table being pointed to
        on_delete:   CASCADE or None — delete this row when parent is deleted
        on_update:   CASCADE or None — update this value when parent PK changes

        Persists the FK definition to schema immediately.
        """
        col_names = [col[0] for col in self.columns]
        if column_name not in col_names:
            raise ValueError(f"Column '{column_name}' does not exist.")

        fk = {
            "column":     column_name,
            "ref_table":  ref_table,
            "ref_column": ref_column,
            "on_delete":  on_delete,
            "on_update":  on_update,
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
        All conditions must be satisfied (AND logic at the top level).
        OR logic is handled inside individual condition dicts.
        """
        for condition in conditions:
            if not Expression.evaluate(condition, row, column_index):
                return False
        return True

    def _validate_not_null(self, row: list):
        """
        Enforce NOT NULL constraints on a row before insert or update.
        Raises ValueError if any NOT NULL column contains None.
        """
        column_index = self._build_column_index()
        for col in self.not_null_columns:
            if col in column_index:
                if row[column_index[col]] is None:
                    raise ValueError(f"Column '{col}' cannot be NULL.")

    def _validate_check_constraints(self, row: list):
        """
        Enforce all CHECK constraints on a row before insert or update.
        Raises ValueError if any constraint is violated.
        """
        column_index = self._build_column_index()

        for constraint in self.check_constraints:
            col   = constraint["column"]
            op    = constraint["op"]
            value = constraint["value"]

            if col not in column_index:
                continue

            cell   = row[column_index[col]]
            passed = False

            if op == ">"  and cell > value:  passed = True
            if op == ">=" and cell >= value: passed = True
            if op == "<"  and cell < value:  passed = True
            if op == "<=" and cell <= value: passed = True
            if op == "="  and cell == value: passed = True
            if op == "!=" and cell != value: passed = True

            if not passed:
                raise ValueError(
                    f"CHECK constraint violated: '{col}' {op} {value!r} "
                    f"(got {cell!r})."
                )

    def _validate_composite_primary_key(self, row: list):
        """
        Enforce composite PRIMARY KEY uniqueness on insert.
        The combination of values across all key columns must be unique.
        Raises ValueError if a duplicate composite key is found.
        """
        if not self.composite_primary_key:
            return

        column_index = self._build_column_index()
        key_values   = tuple(row[column_index[col]] for col in self.composite_primary_key)

        for existing_row in self.rows:
            existing_key = tuple(
                existing_row[column_index[col]]
                for col in self.composite_primary_key
            )
            if existing_key == key_values:
                raise ValueError(
                    f"Duplicate composite PRIMARY KEY: "
                    f"{dict(zip(self.composite_primary_key, key_values))}."
                )

    def _validate_composite_unique(self, row: list, exclude_row: list = None):
        """
        Enforce all composite UNIQUE constraints on a row.
        Each constraint is a list of column names whose combined values must be unique.
        exclude_row is the original row being updated, excluded from duplicate check.
        Raises ValueError if any composite unique constraint is violated.
        """
        if not self.composite_unique:
            return

        column_index = self._build_column_index()

        for key_cols in self.composite_unique:
            key_values = tuple(row[column_index[col]] for col in key_cols)

            for existing_row in self.rows:
                if exclude_row is not None and existing_row == exclude_row:
                    continue
                existing_key = tuple(
                    existing_row[column_index[col]] for col in key_cols
                )
                if existing_key == key_values:
                    raise ValueError(
                        f"Duplicate value for composite UNIQUE "
                        f"({', '.join(key_cols)}): {key_values}."
                    )

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

            ref_table     = db.tables[ref_name]
            ref_col_index = ref_table._build_column_index()

            if ref_col not in ref_col_index:
                raise ValueError(
                    f"Referenced column '{ref_col}' does not exist "
                    f"in table '{ref_name}'."
                )

            ref_idx = ref_col_index[ref_col]
            exists  = any(
                existing_row[ref_idx] == value
                for existing_row in ref_table.rows
            )

            if not exists:
                raise ValueError(
                    f"Foreign key violation: '{col}' value {value!r} "
                    f"does not exist in '{ref_name}.{ref_col}'."
                )

    def _apply_cascade_delete(self, deleted_rows: list, db):
        """
        After rows are deleted from this table, find all child tables
        that have ON DELETE CASCADE FK references to this table and
        delete the corresponding child rows automatically.
        db is needed to look up other tables.
        """
        if db is None:
            return

        for child_table in db.tables.values():
            for fk in child_table.foreign_keys:
                if (
                    fk["ref_table"] == self.name
                    and fk.get("on_delete") == "CASCADE"
                ):
                    ref_col = fk["ref_column"]
                    fk_col  = fk["column"]

                    col_idx     = self._build_column_index().get(ref_col)
                    fk_col_idx  = child_table._build_column_index().get(fk_col)

                    if col_idx is None or fk_col_idx is None:
                        continue

                    deleted_values = {row[col_idx] for row in deleted_rows}

                    child_conditions = [{
                        "type":   "in",
                        "column": fk_col,
                        "values": list(deleted_values)
                    }]

                    child_table.delete(child_conditions, db=db)

    def _apply_cascade_update(self, old_rows: list, new_rows: list, db):
        """
        After rows are updated in this table, find all child tables
        that have ON UPDATE CASCADE FK references to this table and
        update the FK values in matching child rows automatically.
        db is needed to look up other tables.
        """
        if db is None:
            return

        for child_table in db.tables.values():
            for fk in child_table.foreign_keys:
                if (
                    fk["ref_table"] == self.name
                    and fk.get("on_update") == "CASCADE"
                ):
                    ref_col    = fk["ref_column"]
                    fk_col     = fk["column"]
                    col_idx    = self._build_column_index().get(ref_col)
                    fk_col_idx = child_table._build_column_index().get(fk_col)

                    if col_idx is None or fk_col_idx is None:
                        continue

                    for old_row, new_row in zip(old_rows, new_rows):
                        old_val = old_row[col_idx]
                        new_val = new_row[col_idx]

                        if old_val == new_val:
                            continue

                        child_conditions = [{
                            "type":   "simple",
                            "column": fk_col,
                            "op":     "=",
                            "value":  old_val
                        }]

                        child_table.update(
                            [(fk_col, new_val)],
                            child_conditions,
                            db=db
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
        col_idx      = column_index[column_name]

        self.index_manager.create_index(column_name)
        self.index_manager.rebuild(column_name, self.rows, col_idx)

        schema  = self.schema_manager.read()
        indexes = schema.get("indexes", [])

        if column_name not in indexes:
            indexes.append(column_name)

        self.schema_manager.write(
            self.columns,
            self.unique_columns,
            self.primary_key,
            indexes,
            self.foreign_keys,
            list(self.not_null_columns),
            self.default_values,
            self.check_constraints,
            self.auto_increment,
            self.composite_primary_key,
            self.composite_unique
        )

        return f"Index created on '{column_name}'."

    def insert(self, row: list, db=None):
        """
        Validate and insert a new row into the table.

        Steps in order:
        1. Handle AUTO_INCREMENT injection if PK column is omitted
        2. Apply DEFAULT values for any missing or None columns
        3. Validate column count
        4. Validate types
        5. Enforce NOT NULL constraints
        6. Enforce single column PK not null
        7. Reject exact duplicate rows
        8. Enforce single-column UNIQUE constraints
        9. Enforce composite PRIMARY KEY uniqueness
        10. Enforce composite UNIQUE constraints
        11. Validate CHECK constraints
        12. Validate FK constraints
        13. Append to rows and persist to disk
        14. Update all active indexes
        """
        column_index = self._build_column_index()

        # AUTO_INCREMENT: inject next value if PK column is omitted
        if self.auto_increment is not None:
            ai_col = self.auto_increment["column"]
            ai_idx = column_index[ai_col]

            if len(row) == len(self.columns) - 1:
                next_val = self._get_next_auto_increment()
                row = list(row[:ai_idx]) + [next_val] + list(row[ai_idx:])
            elif len(row) == len(self.columns) and row[ai_idx] is None:
                next_val = self._get_next_auto_increment()
                row = list(row)
                row[ai_idx] = next_val

        # Apply DEFAULT values for columns that are None and have a default
        row = list(row)
        for col_name, _ in self.columns:
            idx = column_index[col_name]
            if idx < len(row) and row[idx] is None and col_name in self.default_values:
                row[idx] = self.default_values[col_name]

        if len(row) != len(self.columns):
            raise ValueError(
                f"Expected {len(self.columns)} values, got {len(row)}."
            )

        for value, (column_name, column_type) in zip(row, self.columns):
            expected_python_type = self.SUPPORTED_TYPES[column_type]
            if value is not None and not isinstance(value, expected_python_type):
                raise TypeError(
                    f"Column '{column_name}' expects type '{column_type}', "
                    f"but got '{type(value).__name__}'."
                )

        self._validate_not_null(row)

        if self.primary_key is not None:
            pk_index = column_index[self.primary_key]
            if row[pk_index] is None:
                raise ValueError(
                    f"PRIMARY KEY column '{self.primary_key}' cannot be NULL."
                )

        if row in self.rows:
            raise ValueError("Duplicate row insertion is not allowed.")

        for unique_col in self.unique_columns:
            idx = column_index[unique_col]
            for existing_row in self.rows:
                if existing_row[idx] == row[idx]:
                    raise ValueError(
                        f"Duplicate value for UNIQUE column '{unique_col}'."
                    )

        self._validate_composite_primary_key(row)
        self._validate_composite_unique(row)
        self._validate_check_constraints(row)
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
        conditions:       list of condition dicts for Expression.evaluate
        order_by:         (column_name, direction) e.g. ("id", "ASC") or None
        limit:            max number of rows to return, or None for all

        Uses B-Tree index for single equality conditions on indexed columns.
        Falls back to full table scan for all other cases.
        LIMIT applied last after filtering, ordering, and projection.
        """
        if selected_columns != ["*"]:
            for col in selected_columns:
                if col not in [c[0] for c in self.columns]:
                    raise ValueError(f"Column '{col}' does not exist.")

        column_index = self._build_column_index()

        for condition in conditions:
            if condition.get("type") == "simple":
                if condition["column"] not in column_index:
                    raise ValueError(
                        f"Column '{condition['column']}' does not exist."
                    )

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
            col           = conditions[0]["column"]
            val           = conditions[0]["value"]
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

    def delete(self, conditions: list, db=None):
        """
        Delete all rows matching ALL conditions.
        Requires at least one WHERE condition.
        Rewrites the .db file after deletion via pager.
        Rebuilds all active B-Tree indexes after rewrite.
        Triggers ON DELETE CASCADE on child tables if db is provided.

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
                    raise ValueError(
                        f"Column '{condition['column']}' does not exist."
                    )

        surviving_rows = []
        deleted_rows   = []

        for row in self.rows:
            if self._matches_conditions(row, conditions, column_index):
                deleted_rows.append(row)
            else:
                surviving_rows.append(row)

        deleted_count = len(deleted_rows)

        if deleted_count > 0:
            self.rows = surviving_rows
            self.pager.rewrite_all_rows(surviving_rows)

            for col in self.index_manager.indexes:
                self.index_manager.rebuild(col, self.rows, column_index[col])

            # Trigger CASCADE deletes in child tables
            self._apply_cascade_delete(deleted_rows, db)

        return deleted_count

    def update(self, assignments: list, conditions: list, db=None):
        """
        Update specific columns in rows matching ALL conditions.
        Requires at least one WHERE condition.

        assignments: list of (column, value) tuples
        conditions:  list of condition dicts for Expression.evaluate
        db:          optional database reference for FK and CASCADE

        Enforces types, NOT NULL, UNIQUE, composite UNIQUE, CHECK, FK constraints.
        Applies DEFAULT values if assignment value is None and default exists.
        Triggers ON UPDATE CASCADE on child tables if db is provided.
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

            if value is None and col in self.default_values:
                value = self.default_values[col]

            expected_type = self.SUPPORTED_TYPES[column_types[col]]
            if value is not None and not isinstance(value, expected_type):
                raise TypeError(
                    f"Column '{col}' expects type '{column_types[col]}', "
                    f"but got '{type(value).__name__}'."
                )

            if col == self.primary_key and value is None:
                raise ValueError(
                    f"PRIMARY KEY column '{self.primary_key}' cannot be set to NULL."
                )

            if col in self.not_null_columns and value is None:
                raise ValueError(f"Column '{col}' cannot be set to NULL.")

        for condition in conditions:
            if condition.get("type") == "simple":
                if condition["column"] not in column_index:
                    raise ValueError(
                        f"Column '{condition['column']}' does not exist."
                    )

        updated_count = 0
        updated_rows  = []
        old_rows      = []

        for row in self.rows:
            if self._matches_conditions(row, conditions, column_index):
                new_row = list(row)

                for col, value in assignments:
                    if value is None and col in self.default_values:
                        value = self.default_values[col]

                    if col in self.unique_columns:
                        idx = column_index[col]
                        for existing_row in self.rows:
                            if existing_row[idx] == value and existing_row != row:
                                raise ValueError(
                                    f"Duplicate value for UNIQUE column '{col}'."
                                )

                    new_row[column_index[col]] = value

                self._validate_composite_unique(new_row, exclude_row=row)
                self._validate_check_constraints(new_row)
                self._validate_foreign_keys(new_row, db)

                old_rows.append(row)
                updated_rows.append(new_row)
                updated_count += 1
            else:
                updated_rows.append(row)

        if updated_count > 0:
            self.rows = updated_rows
            self.pager.rewrite_all_rows(updated_rows)

            for col in self.index_manager.indexes:
                self.index_manager.rebuild(col, self.rows, column_index[col])

            # Trigger CASCADE updates in child tables
            new_matched = [r for r in updated_rows if r in updated_rows]
            self._apply_cascade_update(old_rows, updated_rows[:updated_count], db)

        return updated_count