class Transaction:
    """
    Represents an active transaction -a buffered list of operations
    that are either all committed or all rolled back.

    Atomicity is enforced by validating all operations before applying any.
    If any operation fails validation, nothing is written to disk or memory.

    Each operation is stored as a dict:
    {
        "type": "insert" | "delete" | "update",
        "table": table_name,
        "args": operation-specific arguments
    }
    """

    def __init__(self):
        self.operations = []
        self.active = True

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

    def commit(self, db) -> list:
        """
        Commit all buffered operations atomically.

        Phase 1 validates everything. If validation fails, the transaction
        is marked inactive so the user can start fresh without needing ROLLBACK.

        Phase 2 applies all operations only after full validation passes.
        """
        try:
            # Phase 1: validate all operations before touching anything
            self._validate_all(db)
        except Exception:
            # Validation failed - kill the transaction so user can start fresh
            self.operations.clear()
            self.active = False
            raise  # re-raise so the error message still shows

        # Phase 2: apply all operations now that validation passed
        results = []

        for op in self.operations:
            table = db.get_table(op["table"])

            if op["type"] == "insert":
                table.insert(op["args"]["row"], db=db)
                results.append(f"Row inserted into '{op['table']}'.")

            elif op["type"] == "delete":
                count = table.delete(op["args"]["conditions"])
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

        For inserts: checks column count, types, UNIQUE, PK, and FK constraints.
        For updates: checks types, UNIQUE, and FK constraints.
        For deletes: checks that condition columns exist.

        Uses a snapshot of in-memory rows so validation reflects the
        actual committed state, not partial transaction state.
        """
        for op in self.operations:
            table     = db.get_table(op["table"])
            op_type   = op["type"]

            if op_type == "insert":
                row = op["args"]["row"]

                # Column count check
                if len(row) != len(table.columns):
                    raise ValueError(
                        f"Expected {len(table.columns)} values, got {len(row)}."
                    )

                # Type check
                for value, (col_name, col_type) in zip(row, table.columns):
                    expected = table.SUPPORTED_TYPES[col_type]
                    if not isinstance(value, expected):
                        raise TypeError(
                            f"Column '{col_name}' expects '{col_type}', "
                            f"got '{type(value).__name__}'."
                        )

                # NOT NULL on PK
                if table.primary_key is not None:
                    pk_idx = next(
                        i for i, (n, _) in enumerate(table.columns)
                        if n == table.primary_key
                    )
                    if row[pk_idx] is None:
                        raise ValueError(
                            f"PRIMARY KEY column '{table.primary_key}' cannot be NULL."
                        )

                # Duplicate row check
                if row in table.rows:
                    raise ValueError("Duplicate row insertion is not allowed.")

                # UNIQUE constraints
                col_index = table._build_column_index()
                for unique_col in table.unique_columns:
                    idx = col_index[unique_col]
                    for existing in table.rows:
                        if existing[idx] == row[idx]:
                            raise ValueError(
                                f"Duplicate value for UNIQUE column '{unique_col}'."
                            )

                # FK constraints
                table._validate_foreign_keys(row, db)

            elif op_type == "update":
                assignments = op["args"]["assignments"]
                col_index   = table._build_column_index()
                col_types   = {name: ctype for name, ctype in table.columns}

                for col, value in assignments:
                    if col not in col_index:
                        raise ValueError(f"Column '{col}' does not exist.")

                    expected = table.SUPPORTED_TYPES[col_types[col]]
                    if not isinstance(value, expected):
                        raise TypeError(
                            f"Column '{col}' expects '{col_types[col]}', "
                            f"got '{type(value).__name__}'."
                        )

                    if col == table.primary_key and value is None:
                        raise ValueError(
                            f"PRIMARY KEY column '{table.primary_key}' cannot be NULL."
                        )

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
        Discard all buffered operations.
        Nothing was written to disk so nothing needs to be undone.
        """
        self.operations.clear()
        self.active = False