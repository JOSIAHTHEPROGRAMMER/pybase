from .btree import BTree
from .hash_index import HashIndex

class IndexManager:
    """
    Owns all B-Tree indexes for a single table.
    Sits between Table and BTree - Table never touches BTree directly.

    indexes: { column_name: BTree }
    """

    def __init__(self):
        self.indexes      = {}
        self.hash_indexes = {}

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
        Returns None if no index exists on this column - signals table scan needed.
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


    def create_composite_index(self, cols: tuple):
        # cols is a tuple of column names, used as the index key
        if cols in self.indexes:
            raise ValueError(f"Composite index on {cols} already exists.")
        self.indexes[cols] = BTree()

    def has_composite_index(self, cols: tuple) -> bool:
        return cols in self.indexes

    def rebuild_composite(self, cols: tuple, rows: list, col_indexes: list):
        # rebuilds composite index from scratch, col_indexes is list of int positions
        self.indexes[cols] = BTree()
        for row in rows:
            key = tuple(row[i] for i in col_indexes)
            self.indexes[cols].insert(key, row)

    def create_hash_index(self, column_name: str):
        if column_name in self.hash_indexes:
            raise ValueError(f"Hash index on '{column_name}' already exists.")
        self.hash_indexes[column_name] = HashIndex()

    def has_hash_index(self, column_name: str) -> bool:
        return column_name in self.hash_indexes

    def search_hash(self, column_name: str, key) -> list:
        if column_name not in self.hash_indexes:
            return None
        return self.hash_indexes[column_name].search(key)

    def rebuild_hash(self, column_name: str, rows: list, col_idx: int):
        self.hash_indexes[column_name] = HashIndex()
        self.hash_indexes[column_name].rebuild(rows, col_idx)