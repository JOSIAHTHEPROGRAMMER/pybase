import os
from core.table import Table
from storage.schema_manager import SchemaManager
from core.transaction import Transaction


class Database:
    def __init__(self, folder: str = "data"):
        self.folder = folder
        self.tables = {}
        self.current_transaction = None  # None means no active transaction
        self._reload_existing_tables()

    def _reload_existing_tables(self):
        """
        On startup, scan the data folder for .schema files and
        rehydrate all previously created tables automatically.
        """
        if not os.path.exists(self.folder):
            return

        for filename in os.listdir(self.folder):
            if filename.endswith(".schema"):
                table_name = filename[: -len(".schema")]
                schema_manager = SchemaManager(table_name, self.folder)
                schema = schema_manager.read()

                columns = [tuple(col) for col in schema["columns"]]

                # unique_columns=None signals reopen — load from schema
                table = Table(table_name, columns, unique_columns=None)
                self.tables[table_name] = table

    def create_table(self, name: str, columns: list[tuple[str, str]]):
        if name in self.tables:
            raise ValueError(f"Table '{name}' already exists.")

        # unique_columns=set() signals fresh creation
        table = Table(name, columns, unique_columns=set())
        self.tables[name] = table
        return table

    def get_table(self, name: str):
        if name not in self.tables:
            raise ValueError(f"Table '{name}' does not exist.")
        return self.tables[name]

    def drop_table(self, name: str):
        """
        Remove a table entirely — from memory and from disk.
        Deletes both the .db row file and .schema metadata file.
        Raises if the table doesn't exist.
        """
        if name not in self.tables:
            raise ValueError(f"Table '{name}' does not exist.")

        table = self.tables[name]

        # Remove row data file from disk
        if os.path.exists(table.pager.file_path):
            os.remove(table.pager.file_path)

        # Remove schema metadata file from disk
        if os.path.exists(table.schema_manager.schema_path):
            os.remove(table.schema_manager.schema_path)

        # Remove from in-memory registry
        del self.tables[name]

    def begin_transaction(self):
        """
        Start a new transaction.
        Raises if one is already active — nested transactions not supported yet.
        """
        if self.current_transaction is not None and self.current_transaction.active:
            raise ValueError(
                "A transaction is already active. "
                "COMMIT or ROLLBACK before starting a new one."
            )
        self.current_transaction = Transaction()

    def commit_transaction(self) -> list:
        """
        Commit the active transaction — apply all buffered operations.
        Returns result strings for the CLI to display.
        """
        if self.current_transaction is None or not self.current_transaction.active:
            raise ValueError("No active transaction to commit.")

        results = self.current_transaction.commit(self)
        self.current_transaction = None
        return results

    def rollback_transaction(self):
        """
        Rollback the active transaction — discard all buffered operations.
        Nothing was written to disk so nothing needs to be undone.
        """
        if self.current_transaction is None or not self.current_transaction.active:
            raise ValueError("No active transaction to rollback.")

        self.current_transaction.rollback()
        self.current_transaction = None

    def in_transaction(self) -> bool:
        """
        Check if a transaction is currently active.
        Used by CLI to decide whether to buffer or execute immediately.
        """
        return (
            self.current_transaction is not None
            and self.current_transaction.active
        )
