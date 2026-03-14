import os
from core.table import Table
from storage.schema_manager import SchemaManager


class Database:
    def __init__(self, folder: str = "data"):
        self.folder = folder
        self.tables = {}
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

                # Pass unique_columns=None to signal: load from schema, don't rewrite
                table = Table(table_name, columns, unique_columns=None)
                self.tables[table_name] = table

    def create_table(self, name: str, columns: list[tuple[str, str]]):
        if name in self.tables:
            raise ValueError(f"Table '{name}' already exists.")

        # Pass empty set - schema will be written by Table.__init__
        # Constraints are added afterward via add_unique_constraint()
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