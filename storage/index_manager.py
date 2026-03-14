from .btree import BTree


class IndexManager:
    """
    Owns all B-Tree indexes for a single table.
    Sits between Table and BTree — Table never touches BTree directly.

    indexes: { column_name: BTree }
    """

    def __init__(self):
        self.indexes = {}

    def create_index(self, column_name: str):
        """
        Create a new empty B-Tree index for a column.
        Called at CREATE INDEX time or when loading a table with existing indexes.
        """
        if column_name in self.indexes:
            raise ValueError(f"Index on '{column_name}' already exists.")

        self.indexes[column_name] = BTree()

    def has_index(self, column_name: str) -> bool:
        return column_name in self.indexes

    def index_row(self, column_name: str, key, row: list):
        """
        Insert a row into the index for column_name.
        Called on every table insert for indexed columns.
        """
        if column_name in self.indexes:
            self.indexes[column_name].insert(key, row)

    def remove_row(self, column_name: str, key, row: list):
        """
        Remove a row from the index.
        Called on delete and before update applies new values.
        """
        if column_name in self.indexes:
            self.indexes[column_name].delete(key, row)

    def search(self, column_name: str, key) -> list:
        """
        Return all rows matching key in the index.
        Returns None if no index exists on this column — signals table scan needed.
        """
        if column_name not in self.indexes:
            return None  # None = no index, [] = index exists but no match

        return self.indexes[column_name].search(key)

    def rebuild(self, column_name: str, rows: list, col_idx: int):
        """
        Rebuild an index from scratch using current rows.
        Called after bulk operations like delete/update that rewrite the pager.
        """
        self.indexes[column_name] = BTree()

        for row in rows:
            self.indexes[column_name].insert(row[col_idx], row)