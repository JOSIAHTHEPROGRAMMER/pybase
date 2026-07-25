import os
from core.table import Table
from storage.schema_manager import SchemaManager
from core.transaction import Transaction
import json

JSON_COMPATIBLE_BASE_TYPES = {"int", "float", "boolean", "string", "varchar", "char", "text"}


class Database:
    def __init__(self, folder: str = "data"):
        self.folder = folder
        self.tables = {}
        self.views  = {}
        self.procedures = {}
        self.custom_types = {}
        self.current_transaction = None
        self._reload_existing_tables()
        self._reload_existing_views()
        self._reload_existing_custom_types()
        self._reload_existing_procedures()

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

                # Pass folder so Table writes files to the correct location
                table = Table(table_name, columns, unique_columns=None, folder=self.folder)
                self.tables[table_name] = table

    def _reload_existing_views(self):
        # load views.json from disk if it exists
        views_path = os.path.join(self.folder, "views.json")
        if os.path.exists(views_path):
            
            with open(views_path, "r") as f:
                self.views = json.load(f)


    def _reload_existing_custom_types(self):
        types_path = os.path.join(self.folder, "custom_types.json")
        if os.path.exists(types_path):
            with open(types_path, "r") as f:
                self.custom_types = json.load(f)

    def _persist_custom_types(self):
        types_path = os.path.join(self.folder, "custom_types.json")
        with open(types_path, "w") as f:
            json.dump(self.custom_types, f, indent=2)



    def _reload_existing_procedures(self):
        procedures_path = os.path.join(self.folder, "procedures.json")
        if os.path.exists(procedures_path):
            with open(procedures_path, "r") as f:
                self.procedures = json.load(f)

    def _persist_procedures(self):
        procedures_path = os.path.join(self.folder, "procedures.json")
        with open(procedures_path, "w") as f:
            json.dump(self.procedures, f, indent=2)




    def _persist_views(self):

        views_path = os.path.join(self.folder, "views.json")
        with open(views_path, "w") as f:
            json.dump(self.views, f, indent=2)

    def create_table(self, name: str, columns: list[tuple[str, str]]):
        if name in self.tables:
            raise ValueError(f"Table '{name}' already exists.")

        # Pass folder so Table writes files to the correct location
        table = Table(name, columns, unique_columns=set(), folder=self.folder)
        self.tables[name] = table
        return table

    def get_table(self, name: str):
        if name not in self.tables:
            raise ValueError(f"Table '{name}' does not exist.")
        return self.tables[name]

    def drop_table(self, name: str):
        """
        Remove a table entirely - from memory and from disk.
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

    def drop_database(self):
        """
        Destroy all tables and wipe all persisted data from disk.
        Equivalent to dropping every table at once plus clearing history,
        views, custom types, and stored procedures.
        The data folder is kept so the engine can restart cleanly.
        Used for a full reset of the database state.
        """
        # Drop every table cleanly using existing drop_table logic
        for table_name in list(self.tables.keys()):
            table = self.tables[table_name]

            if os.path.exists(table.pager.file_path):
                os.remove(table.pager.file_path)

            if os.path.exists(table.schema_manager.schema_path):
                os.remove(table.schema_manager.schema_path)

        # Clear in-memory registry
        self.tables.clear()

        # Clear views, custom types, and stored procedures, in memory and on disk
        self.views.clear()
        self.custom_types.clear()
        self.procedures.clear()

        for filename in ("views.json", "custom_types.json", "procedures.json"):
            path = os.path.join(self.folder, filename)
            if os.path.exists(path):
                os.remove(path)

        # Wipe query history file if it exists
        history_path = os.path.join(self.folder, "history.json")
        if os.path.exists(history_path):
            os.remove(history_path)



    def create_view(self, name: str, select_sql: str, replace: bool = False):
        if name in self.tables:
            raise ValueError(f"A table named '{name}' already exists.")
        if name in self.views and not replace:
            raise ValueError(f"View '{name}' already exists. Use CREATE OR REPLACE VIEW.")
        self.views[name] = select_sql
        self._persist_views()

    def drop_view(self, name: str):
        if name not in self.views:
            raise ValueError(f"View '{name}' does not exist.")
        del self.views[name]
        self._persist_views()

    def get_view(self, name: str) -> str:
        if name not in self.views:
            raise ValueError(f"View '{name}' does not exist.")
        return self.views[name]





    def create_procedure(self, name: str, params: list, body: list):
        if name in self.tables:
            raise ValueError(f"A table named '{name}' already exists.")
        if name in self.procedures:
            raise ValueError(f"Procedure '{name}' already exists.")
        if not body:
            raise ValueError("CREATE PROCEDURE requires at least one statement.")

        self.procedures[name] = {"params": params, "body": body}
        self._persist_procedures()

    def drop_procedure(self, name: str):
        if name not in self.procedures:
            raise ValueError(f"Procedure '{name}' does not exist.")
        del self.procedures[name]
        self._persist_procedures()

    def has_procedure(self, name: str) -> bool:
        return name in self.procedures

    def get_procedure(self, name: str) -> dict:
        if name not in self.procedures:
            raise ValueError(f"Procedure '{name}' does not exist.")
        return self.procedures[name]



    def create_type(self, name: str, fields: list):
        if name in self.tables:
            raise ValueError(f"A table named '{name}' already exists.")
        if name in self.views:
            raise ValueError(f"A view named '{name}' already exists.")
        if name in self.custom_types:
            raise ValueError(f"Type '{name}' already exists.")
        if not fields:
            raise ValueError("CREATE TYPE requires at least one field.")

        for field_name, field_type in fields:
            base = field_type.split("(")[0]
            if base not in JSON_COMPATIBLE_BASE_TYPES and base not in self.custom_types:
                raise ValueError(
                    f"Field '{field_name}' has unsupported type '{field_type}' for type '{name}'. "
                    "Composite type fields must be int, float, boolean, string, varchar, "
                    "char, text, or another existing custom type."
                )

        self.custom_types[name] = fields
        self._persist_custom_types()

    def drop_type(self, name: str):
        if name not in self.custom_types:
            raise ValueError(f"Type '{name}' does not exist.")

        for table_name, table in self.tables.items():
            for col_name, type_name in table.custom_type_columns.items():
                if type_name == name:
                    raise ValueError(
                        f"Cannot drop type '{name}': in use by column "
                        f"'{col_name}' in table '{table_name}'."
                    )

        for other_name, fields in self.custom_types.items():
            if other_name == name:
                continue
            for field_name, field_type in fields:
                if field_type.split("(")[0] == name:
                    raise ValueError(
                        f"Cannot drop type '{name}': referenced as a field "
                        f"in type '{other_name}'."
                    )

        del self.custom_types[name]
        self._persist_custom_types()

    def has_custom_type(self, name: str) -> bool:
        return name in self.custom_types

    def validate_composite_value(self, type_name: str, value, field_path: str = None):
        """
        Recursively validate a JSON-decoded value against a registered
        composite type definition. Raises ValueError on any mismatch.
        """
        if type_name not in self.custom_types:
            raise ValueError(f"Unknown type '{type_name}'.")

        label = field_path or type_name
        fields = self.custom_types[type_name]

        if not isinstance(value, dict):
            raise ValueError(
                f"Value for type '{label}' must be a JSON object, got {type(value).__name__}."
            )

        field_names = [f[0] for f in fields]
        extra = set(value.keys()) - set(field_names)
        if extra:
            raise ValueError(f"Unexpected fields {sorted(extra)} for type '{label}'.")

        for field_name, field_type in fields:
            if field_name not in value:
                raise ValueError(f"Missing field '{field_name}' for type '{label}'.")

            field_value = value[field_name]
            if field_value is None:
                continue

            base = field_type.split("(")[0]
            if base in self.custom_types:
                self.validate_composite_value(base, field_value, f"{label}.{field_name}")
            else:
                expected = Table.SUPPORTED_TYPES.get(base)
                if expected and not isinstance(field_value, expected):
                    raise ValueError(
                        f"Field '{field_name}' of type '{label}' expects "
                        f"'{field_type}', got {type(field_value).__name__}."
                    )

    def rename_table(self, old_name: str, new_name: str):
        if old_name not in self.tables:
            raise ValueError(f"Table '{old_name}' does not exist.")
        if new_name in self.tables:
            raise ValueError(f"Table '{new_name}' already exists.")
        table = self.tables[old_name]
        table.rename(new_name)
        self.tables[new_name] = table
        del self.tables[old_name]

    def begin_transaction(self):
        """
        Start a new transaction.
        Raises if one is already active - nested transactions not supported yet.
        """
        if self.current_transaction is not None and self.current_transaction.active:
            raise ValueError(
                "A transaction is already active. "
                "COMMIT or ROLLBACK before starting a new one."
            )
        self.current_transaction = Transaction()

    def commit_transaction(self) -> list:
        """
        Commit the active transaction - apply all buffered operations.
        Returns result strings for the CLI to display.
        """
        if self.current_transaction is None or not self.current_transaction.active:
            raise ValueError("No active transaction to commit.")

        results = self.current_transaction.commit(self)
        self.current_transaction = None
        return results

    def rollback_transaction(self):
        """
        Rollback the active transaction - discard all buffered operations.
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