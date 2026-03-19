import json
import os


class SchemaManager:
    """
    Handles reading and writing table schema to disk.
    Each table gets a JSON file: data/<table_name>.schema

    Schema format:
    {
        "columns": [["id", "int"], ["name", "string"]],
        "unique_columns": ["id"],
        "primary_key": "id",
        "indexes": [],
        "foreign_keys": [
            {"column": "dept_id", "ref_table": "departments", "ref_column": "id"}
        ]
    }
    """

    def __init__(self, table_name: str, folder: str = "data"):
        self.table_name = table_name
        self.folder = folder
        self.schema_path = os.path.join(folder, f"{table_name}.schema")

        if not os.path.exists(folder):
            os.makedirs(folder)

    def write(self, columns, unique_columns, primary_key=None,
              indexes=None, foreign_keys=None):
        """
        Persist schema to disk including foreign key definitions.
        """
        schema = {
            "columns":      [list(col) for col in columns],
            "unique_columns": list(unique_columns),
            "primary_key":  primary_key,
            "indexes":      indexes or [],
            "foreign_keys": foreign_keys or [],
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
        """
        return os.path.exists(self.schema_path)