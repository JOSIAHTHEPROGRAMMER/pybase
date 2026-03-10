import json
import os


class SchemaManager:
    """
    Handles reading and writing table schema to disk.
    Each table gets a JSON file: data/<table_name>.schema

    Schema format:
    {
        "columns": [["id", "int"], ["name", "string"]],
        "unique_columns": ["id"]
    }
    """

    def __init__(self, table_name: str, folder: str = "data"):
        self.table_name = table_name
        self.folder = folder
        self.schema_path = os.path.join(folder, f"{table_name}.schema")

        if not os.path.exists(folder):
            os.makedirs(folder)

    def write(self, columns: list[tuple[str, str]], unique_columns: set):
        """
        Persist schema to disk. Called once at table creation.
        """
        schema = {
            "columns": [list(col) for col in columns],
            "unique_columns": list(unique_columns),
        }
        with open(self.schema_path, "w") as f:
            json.dump(schema, f, indent=2)

    def read(self) -> dict:
        """
        Load schema from disk. Raises if schema file is missing.
        """
        if not os.path.exists(self.schema_path):
            raise FileNotFoundError(
                f"No schema found for table '{self.table_name}'. "
                "Was it created in a previous session?"
            )
        with open(self.schema_path, "r") as f:
            return json.load(f)

    def exists(self) -> bool:
        """
        Check if a schema file already exists on disk.
        Used by Database to detect pre-existing tables.
        """
        return os.path.exists(self.schema_path)