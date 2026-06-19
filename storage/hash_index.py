class HashIndex:
    """
    Simple dict-based index for O(1) average equality lookups.
    No range support, use B-Tree for that.
    """

    def __init__(self):
        self.data = {}

    def insert(self, key, row: list):
        # hash None as a special sentinel so NULL values are indexable
        k = key if key is not None else "__null__"
        if k not in self.data:
            self.data[k] = []
        self.data[k].append(row)

    def search(self, key) -> list:
        k = key if key is not None else "__null__"
        return self.data.get(k, [])

    def delete(self, key, row: list):
        k = key if key is not None else "__null__"
        if k in self.data:
            if row in self.data[k]:
                self.data[k].remove(row)
            if not self.data[k]:
                del self.data[k]

    def rebuild(self, rows: list, col_idx: int):
        self.data = {}
        for row in rows:
            self.insert(row[col_idx], row)