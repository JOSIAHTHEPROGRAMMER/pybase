import os
from .serializer import Serializer


class Pager:
    def __init__(self, table_name: str, columns: list[tuple[str, str]], folder="data"):
        """
        Initialize pager for a table.
        Creates folder if it doesn't exist.
        Each table gets its own file: table_name.db
        Rows are variable length, so there is no fixed row_size anymore.
        """
        self.table_name = table_name
        self.columns    = columns
        self.folder     = folder
        self.file_path  = os.path.join(folder, f"{table_name}.db")

        if not os.path.exists(folder):
            os.makedirs(folder)

        if not os.path.exists(self.file_path):
            open(self.file_path, "wb").close()

    def append_row(self, row: list):
        """
        Serialize and append a row to the file.
        Format is tombstone byte, then 4 byte length, then row content.
        """
        content = Serializer.serialize_row(row, self.columns)
        length_prefix = len(content).to_bytes(4, byteorder="big")
        data = b'\x00' + length_prefix + content

        with open(self.file_path, "ab") as f:
            f.write(data)

    def load_all_rows(self):
        """
        Walk the file from the start and load every alive row.
        Returns a tuple of rows and offsets, where offsets[i] is the
        byte position of the tombstone byte for rows[i].
        Tombstoned rows are skipped but the offset still advances correctly.
        """
        rows    = []
        offsets = []

        with open(self.file_path, "rb") as f:
            while True:
                row_start = f.tell()

                tombstone = f.read(1)
                if not tombstone:
                    break

                length_bytes = f.read(4)
                length = int.from_bytes(length_bytes, byteorder="big")

                content = f.read(length)

                if tombstone[0] == 0xFF:
                    continue

                row = Serializer.deserialize_row(content, self.columns)
                rows.append(row)
                offsets.append(row_start)

        return rows, offsets

    def delete_row_at(self, offset: int):
        """
        Write a tombstone byte at the given offset.
        offset must point at the tombstone byte position of a row.
        """
        with open(self.file_path, "r+b") as f:
            f.seek(offset)
            f.write(b'\xFF')

    def compact(self):
        """
        Rewrite the file keeping only alive rows.
        Reuses load_all_rows logic by walking the file directly so
        tombstoned rows never get re-serialized.
        """
        alive_rows = []

        with open(self.file_path, "rb") as f:
            while True:
                tombstone = f.read(1)
                if not tombstone:
                    break

                length_bytes = f.read(4)
                length = int.from_bytes(length_bytes, byteorder="big")
                content = f.read(length)

                if tombstone[0] != 0xFF:
                    alive_rows.append(Serializer.deserialize_row(content, self.columns))

        with open(self.file_path, "wb") as f:
            for row in alive_rows:
                content = Serializer.serialize_row(row, self.columns)
                length_prefix = len(content).to_bytes(4, byteorder="big")
                f.write(b'\x00' + length_prefix + content)

    def rewrite_all_rows(self, rows: list):
        """
        Overwrite the entire file with the given rows, all marked alive.
        Used by truncate, alter table, and update.
        """
        with open(self.file_path, "wb") as f:
            for row in rows:
                content = Serializer.serialize_row(row, self.columns)
                length_prefix = len(content).to_bytes(4, byteorder="big")
                f.write(b'\x00' + length_prefix + content)