import os
from .serializer import Serializer


class Pager:
    def __init__(self, table_name: str, columns: list[tuple[str, str]], folder="data"):
        """
        Initialize pager for a table.
        Creates folder if it doesn't exist.
        Each table gets its own file: table_name.db
        """
        self.table_name = table_name
        self.columns = columns
        self.folder = folder
        self.file_path = os.path.join(folder, f"{table_name}.db")

        if not os.path.exists(folder):
            os.makedirs(folder)

        # create empty file if not exists
        if not os.path.exists(self.file_path):
            open(self.file_path, "wb").close()

        self.row_size = self._calculate_row_size()

    def _calculate_row_size(self):
        """
        Calculate the fixed byte size of a single row based on column types.
    
        """
        size = 0
        for _, column_type in self.columns:
            if column_type == "int":
                size += 4
            elif column_type == "bigint":
                size += 8
            elif column_type == "float":
                size += 8
            elif column_type == "boolean":
                size += 1
            elif column_type == "string":
                size += 1 + Serializer.STRING_SIZE
        return size

    def append_row(self, row: list):
        """
        Serialize and append a row to the file.
        """
        data = Serializer.serialize_row(row, self.columns)
        with open(self.file_path, "ab") as f:
            f.write(data)

    def load_all_rows(self):
        """
        Load all rows from file and return as list.
        """
        rows = []
        with open(self.file_path, "rb") as f:
            while True:
                chunk = f.read(self.row_size)
                if not chunk:
                    break
                row = Serializer.deserialize_row(chunk, self.columns)
                rows.append(row)
        return rows
    
    def rewrite_all_rows(self, rows: list):
        """
        Overwrite the entire .db file with the given rows.
        Used after deletions. Simple but correct - optimization comes later.
        """
        with open(self.file_path, "wb") as f:
            for row in rows:
                data = Serializer.serialize_row(row, self.columns)
                f.write(data)