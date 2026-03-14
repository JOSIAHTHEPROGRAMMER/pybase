class Transaction:
    """
    Represents an active transaction — a buffered list of operations
    that are either all committed or all rolled back.

    Each operation is stored as a dict:
    {
        "type": "insert" | "delete" | "update",
        "table": table_name,
        "args": operation-specific arguments
    }

    The transaction never touches disk directly — it delegates to
    Table methods at commit time.
    """

    def __init__(self):
        # Buffer of pending operations — applied only on commit
        self.operations = []
        self.active = True

    def add(self, op_type: str, table_name: str, **kwargs):
        """
        Buffer an operation for later execution.
        op_type: "insert", "delete", or "update"
        """
        self.operations.append({
            "type": op_type,
            "table": table_name,
            "args": kwargs
        })

    def commit(self, db) -> list:
        """
        Apply all buffered operations against the live database.
        Returns a list of result strings for the CLI to display.

        If any operation fails, raises immediately — partial state
        is possible in this implementation (full rollback on error
        requires savepoints, which come later).
        """
        results = []

        for op in self.operations:
            table = db.get_table(op["table"])

            if op["type"] == "insert":
                table.insert(op["args"]["row"])
                results.append(f"Row inserted into '{op['table']}'.")

            elif op["type"] == "delete":
                count = table.delete(op["args"]["conditions"])
                results.append(f"{count} row(s) deleted from '{op['table']}'.")

            elif op["type"] == "update":
                count = table.update(
                    op["args"]["assignments"],
                    op["args"]["conditions"]
                )
                results.append(f"{count} row(s) updated in '{op['table']}'.")

        self.active = False
        return results

    def rollback(self):
        """
        Discard all buffered operations.
        Nothing was written to disk so nothing needs to be undone.
        """
        self.operations.clear()
        self.active = False