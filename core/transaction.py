class Transaction:
    """
    Represents an active transaction with full SAVEPOINT support.

    Operations are buffered and applied atomically on COMMIT.
    SAVEPOINTs allow partial rollback within a transaction without
    discarding the entire operation buffer.

    Each operation is stored as a dict:
    {
        "type": "insert" | "delete" | "update",
        "table": table_name,
        "args": operation-specific arguments
    }
    """

    def __init__(self):
        self.operations  = []
        self.savepoints  = {}  # name -> index into operations list at save time
        self.active      = True

    def add(self, op_type: str, table_name: str, **kwargs):
        """
        Buffer an operation for later execution.
        op_type: insert, delete, or update
        """
        self.operations.append({
            "type":  op_type,
            "table": table_name,
            "args":  kwargs
        })

    def savepoint(self, name: str):
        """
        Create a named savepoint at the current position in the operation buffer.
        Rolling back to this savepoint discards all operations added after it.
        Raises if a savepoint with this name already exists.
        """
        if name in self.savepoints:
            raise ValueError(
                f"Savepoint '{name}' already exists. "
                "Release it before creating a new one with the same name."
            )
        self.savepoints[name] = len(self.operations)

    def rollback_to_savepoint(self, name: str):
        """
        Discard all operations buffered after the named savepoint.
        The savepoint itself is kept so it can be rolled back to again.
        Raises if the savepoint does not exist.
        """
        if name not in self.savepoints:
            raise ValueError(f"Savepoint '{name}' does not exist.")

        idx = self.savepoints[name]
        self.operations = self.operations[:idx]

    def release_savepoint(self, name: str):
        """
        Remove a named savepoint without rolling back.
        Operations buffered after the savepoint are kept.
        Raises if the savepoint does not exist.
        """
        if name not in self.savepoints:
            raise ValueError(f"Savepoint '{name}' does not exist.")
        del self.savepoints[name]

    def commit(self, db) -> list:
        """
        Commit all buffered operations atomically.

        Phase 1 validates every operation before Phase 2 applies any.
        If validation fails the transaction is auto-cancelled and nothing lands.
        """
        try:
            self._validate_all(db)
        except Exception:
            self.operations.clear()
            self.savepoints.clear()
            self.active = False
            raise

        results = []

        for op in self.operations:
            table = db.get_table(op["table"])

            if op["type"] == "insert":
                table.insert(op["args"]["row"], db=db)
                results.append(f"Row inserted into '{op['table']}'.")

            elif op["type"] == "delete":
                count = table.delete(op["args"]["conditions"], db=db)
                results.append(f"{count} row(s) deleted from '{op['table']}'.")

            elif op["type"] == "update":
                count = table.update(
                    op["args"]["assignments"],
                    op["args"]["conditions"],
                    db=db
                )
                results.append(f"{count} row(s) updated in '{op['table']}'.")

        self.active = False
        return results

    def _validate_all(self, db):
        """
        Validate every buffered operation without applying any of them.
        Raises on the first violation found.
        """
        for op in self.operations:
            table   = db.get_table(op["table"])
            op_type = op["type"]

            if op_type == "insert":
                row = op["args"]["row"]

                if len(row) != len(table.columns):
                    raise ValueError(
                        f"Expected {len(table.columns)} values, got {len(row)}."
                    )

                for value, (col_name, col_type) in zip(row, table.columns):
                    expected = table.SUPPORTED_TYPES[col_type]
                    if value is not None and not isinstance(value, expected):
                        raise TypeError(
                            f"Column '{col_name}' expects '{col_type}', "
                            f"got '{type(value).__name__}'."
                        )

                if table.primary_key is not None:
                    pk_idx = next(
                        i for i, (n, _) in enumerate(table.columns)
                        if n == table.primary_key
                    )
                    if row[pk_idx] is None:
                        raise ValueError(
                            f"PRIMARY KEY column '{table.primary_key}' cannot be NULL."
                        )

                if row in table.rows:
                    raise ValueError("Duplicate row insertion is not allowed.")

                col_index = table._build_column_index()
                for unique_col in table.unique_columns:
                    idx = col_index[unique_col]
                    for existing in table.rows:
                        if existing[idx] == row[idx]:
                            raise ValueError(
                                f"Duplicate value for UNIQUE column '{unique_col}'."
                            )

                table._validate_not_null(row)
                table._validate_composite_primary_key(row)
                table._validate_composite_unique(row)
                table._validate_check_constraints(row)
                table._validate_foreign_keys(row, db)

            elif op_type == "update":
                assignments = op["args"]["assignments"]
                col_index   = table._build_column_index()
                col_types   = {name: ctype for name, ctype in table.columns}

                for col, value in assignments:
                    if col not in col_index:
                        raise ValueError(f"Column '{col}' does not exist.")

                    expected = table.SUPPORTED_TYPES[col_types[col]]
                    if value is not None and not isinstance(value, expected):
                        raise TypeError(
                            f"Column '{col}' expects '{col_types[col]}', "
                            f"got '{type(value).__name__}'."
                        )

                    if col == table.primary_key and value is None:
                        raise ValueError(
                            f"PRIMARY KEY column '{table.primary_key}' cannot be NULL."
                        )

                    if col in table.not_null_columns and value is None:
                        raise ValueError(f"Column '{col}' cannot be set to NULL.")

            elif op_type == "delete":
                conditions = op["args"]["conditions"]
                col_index  = table._build_column_index()

                for condition in conditions:
                    if condition.get("type") == "simple":
                        if condition["column"] not in col_index:
                            raise ValueError(
                                f"Column '{condition['column']}' does not exist."
                            )

    def rollback(self):
        """
        Discard all buffered operations and all savepoints.
        Nothing was written to disk so nothing needs to be undone.
        """
        self.operations.clear()
        self.savepoints.clear()
        self.active = False