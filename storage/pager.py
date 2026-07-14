import os
import zlib
from .serializer import Serializer
from .page import (
    Page, PAGE_SIZE, PAGE_BODY_SIZE,
    PAGE_TYPE_DATA, PAGE_TYPE_OVERFLOW,
    OVERFLOW_NO_NEXT, OVERFLOW_PTR_SIZE
)

WAL_ENTRY_SIZE = 4 + PAGE_SIZE + 4  # page_num + page data + checksum


class Pager:
    def __init__(self, table_name: str, columns: list[tuple[str, str]], folder="data"):
        self.table_name = table_name
        self.columns    = columns
        self.folder     = folder
        self.file_path  = os.path.join(folder, f"{table_name}.db")
        self.wal_path   = os.path.join(folder, f"{table_name}.wal")
        self.idx_path   = os.path.join(folder, f"{table_name}.idx")

        if not os.path.exists(folder):
            os.makedirs(folder)

        if not os.path.exists(self.file_path):
            open(self.file_path, "wb").close()

        self._recover()

    def _page_count(self) -> int:
        return os.path.getsize(self.file_path) // PAGE_SIZE

    def read_page(self, page_num: int) -> Page:
        with open(self.file_path, "rb") as f:
            f.seek(page_num * PAGE_SIZE)
            data = f.read(PAGE_SIZE)
        if len(data) < PAGE_SIZE:
            raise ValueError(f"Page {page_num} is incomplete or does not exist.")
        return Page.from_bytes(data)

    def write_page(self, page_num: int, page: Page):
        current_count = self._page_count()
        with open(self.file_path, "r+b") as f:
            if page_num >= current_count:
                f.seek(0, 2)
                gap = page_num - current_count
                f.write(bytes(gap * PAGE_SIZE))
            f.seek(page_num * PAGE_SIZE)
            f.write(page.to_bytes())

    def _allocate_page(self, page_type: int = PAGE_TYPE_DATA) -> Page:
        page_num = self._page_count()
        page     = Page(page_num, page_type)
        self.write_page(page_num, page)
        return page

    def _find_first_fit(self, needed: int) -> Page | None:
        for i in range(self._page_count()):
            page = self.read_page(i)
            if page.page_type == PAGE_TYPE_DATA and page.free_space() >= needed:
                return page
        return None

    def _write_wal_entry(self, page_num: int, page: Page):
        data     = page.to_bytes()
        checksum = zlib.crc32(data) & 0xFFFFFFFF
        entry    = (
            page_num.to_bytes(4, byteorder="big") +
            data +
            checksum.to_bytes(4, byteorder="big")
        )
        with open(self.wal_path, "ab") as f:
            f.write(entry)
            f.flush()
            os.fsync(f.fileno())

    def _clear_wal(self):
        with open(self.wal_path, "wb") as f:
            pass

    def _recover(self):
        if not os.path.exists(self.wal_path):
            return
        if os.path.getsize(self.wal_path) == 0:
            return

        with open(self.wal_path, "rb") as f:
            while True:
                entry = f.read(WAL_ENTRY_SIZE)
                if not entry or len(entry) < WAL_ENTRY_SIZE:
                    break

                page_num  = int.from_bytes(entry[:4], byteorder="big")
                page_data = entry[4:4 + PAGE_SIZE]
                expected  = int.from_bytes(entry[4 + PAGE_SIZE:], byteorder="big")
                actual    = zlib.crc32(page_data) & 0xFFFFFFFF

                if expected != actual:
                    break

                with open(self.file_path, "r+b") as db:
                    db.seek(page_num * PAGE_SIZE)
                    db.write(page_data)

        self._clear_wal()

    def _save_idx(self, slot_index: list[tuple[int, int, int]]):
        with open(self.idx_path, "wb") as f:
            f.write(len(slot_index).to_bytes(4, byteorder="big"))
            for page_num, slot_offset, slot_length in slot_index:
                f.write(page_num.to_bytes(4,    byteorder="big"))
                f.write(slot_offset.to_bytes(2, byteorder="big"))
                f.write(slot_length.to_bytes(4, byteorder="big"))

    def _load_idx(self) -> list[tuple[int, int, int]]:
        if not os.path.exists(self.idx_path):
            return []
        with open(self.idx_path, "rb") as f:
            count   = int.from_bytes(f.read(4), byteorder="big")
            entries = []
            for _ in range(count):
                page_num    = int.from_bytes(f.read(4), byteorder="big")
                slot_offset = int.from_bytes(f.read(2), byteorder="big")
                slot_length = int.from_bytes(f.read(4), byteorder="big")
                entries.append((page_num, slot_offset, slot_length))
        return entries

    def _write_row_to_page(self, page: Page, slot_data: bytes) -> tuple[int, int]:
        # write slot to page, log to WAL, persist, return (page_num, slot_offset)
        slot_offset = page.free_offset
        self._write_wal_entry(page.page_number, page)
        page.write_slot(slot_data)
        self.write_page(page.page_number, page)
        self._clear_wal()
        return page.page_number, slot_offset

    def append_row(self, row: list) -> tuple[int, int]:
        content   = Serializer.serialize_row(row, self.columns)
        slot_data = b'\x00' + len(content).to_bytes(4, byteorder="big") + content

        if len(slot_data) <= PAGE_BODY_SIZE - OVERFLOW_PTR_SIZE:
            page = self._find_first_fit(len(slot_data))
            if page is None:
                page = self._allocate_page()
            return self._write_row_to_page(page, slot_data)

        # split across overflow pages, build chunk list first
        chunks    = []
        remaining = slot_data
        first     = True

        while remaining:
            usable = PAGE_BODY_SIZE - OVERFLOW_PTR_SIZE
            if first:
                page  = self._find_first_fit(usable) or self._allocate_page()
                first = False
            else:
                page = self._allocate_page(PAGE_TYPE_OVERFLOW)

            chunk     = remaining[:usable]
            remaining = remaining[usable:]
            chunks.append((page, chunk, len(remaining) == 0))

        # write back to front so each page knows its successor
        next_page_num = OVERFLOW_NO_NEXT
        first_page_num  = 0
        first_slot_offset = 0

        for idx, (page, chunk, is_last) in enumerate(reversed(chunks)):
            self._write_wal_entry(page.page_number, page)

            slot_offset = page.free_offset
            page.body[slot_offset:slot_offset + len(chunk)] = chunk
            page.free_offset += len(chunk)
            page.body[page.free_offset:page.free_offset + 4] = \
                next_page_num.to_bytes(4, byteorder="big")
            page.free_offset += 4

            if page.page_type == PAGE_TYPE_DATA:
                page.row_count   += 1
                first_slot_offset = slot_offset

            self.write_page(page.page_number, page)
            self._clear_wal()
            next_page_num = page.page_number

            if idx == len(chunks) - 1:
                first_page_num = page.page_number

        return first_page_num, first_slot_offset

    def load_all_rows(self) -> tuple[list, list]:
        rows       = []
        slot_index = []

        for i in range(self._page_count()):
            page = self.read_page(i)

            if page.page_type != PAGE_TYPE_DATA:
                continue

            offset = 0
            while offset < page.free_offset:
                tombstone   = page.body[offset]
                slot_length = int.from_bytes(
                    page.body[offset + 1:offset + 5], byteorder="big"
                )
                fits = (1 + 4 + slot_length) <= (PAGE_BODY_SIZE - offset)

                if not fits:
                    first_chunk_size = PAGE_BODY_SIZE - offset - OVERFLOW_PTR_SIZE
                    content          = bytes(page.body[offset:offset + first_chunk_size])
                    next_page_num    = int.from_bytes(
                        page.body[offset + first_chunk_size:offset + first_chunk_size + 4],
                        byteorder="big"
                    )

                    while next_page_num != OVERFLOW_NO_NEXT:
                        ov_page      = self.read_page(next_page_num)
                        ptr_offset   = ov_page.free_offset - OVERFLOW_PTR_SIZE
                        next_page_num = int.from_bytes(
                            ov_page.body[ptr_offset:ptr_offset + 4],
                            byteorder="big"
                        )
                        content += bytes(ov_page.body[:ptr_offset])

                    if tombstone != 0xFF:
                        row = Serializer.deserialize_row(content[5:], self.columns)
                        rows.append(row)
                        slot_index.append((i, offset, PAGE_BODY_SIZE - offset))

                    offset = PAGE_BODY_SIZE

                else:
                    total_slot = 1 + 4 + slot_length
                    if tombstone != 0xFF:
                        content = bytes(page.body[offset + 5:offset + 5 + slot_length])
                        row     = Serializer.deserialize_row(content, self.columns)
                        rows.append(row)
                        slot_index.append((i, offset, total_slot))
                    offset += total_slot

        self._save_idx(slot_index)
        return rows, slot_index

    def delete_row_at(self, page_num: int, slot_offset: int):
        page = self.read_page(page_num)
        self._write_wal_entry(page_num, page)
        page.write_tombstone(slot_offset)
        self.write_page(page_num, page)
        self._clear_wal()

    def compact(self):
        alive_rows = []
        for i in range(self._page_count()):
            page = self.read_page(i)
            if page.page_type != PAGE_TYPE_DATA:
                continue
            offset = 0
            while offset < page.free_offset:
                tombstone   = page.body[offset]
                slot_length = int.from_bytes(
                    page.body[offset + 1:offset + 5], byteorder="big"
                )
                fits       = (1 + 4 + slot_length) <= (PAGE_BODY_SIZE - offset)
                total_slot = 1 + 4 + slot_length

                if not fits:
                    first_chunk_size = PAGE_BODY_SIZE - offset - OVERFLOW_PTR_SIZE
                    content          = bytes(page.body[offset:offset + first_chunk_size])
                    next_page_num    = int.from_bytes(
                        page.body[offset + first_chunk_size:offset + first_chunk_size + 4],
                        byteorder="big"
                    )
                    while next_page_num != OVERFLOW_NO_NEXT:
                        ov_page       = self.read_page(next_page_num)
                        ptr_offset    = ov_page.free_offset - OVERFLOW_PTR_SIZE
                        next_page_num = int.from_bytes(
                            ov_page.body[ptr_offset:ptr_offset + 4],
                            byteorder="big"
                        )
                        content += bytes(ov_page.body[:ptr_offset])
                    if tombstone != 0xFF:
                        alive_rows.append(
                            Serializer.deserialize_row(content[5:], self.columns)
                        )
                    offset = PAGE_BODY_SIZE
                else:
                    if tombstone != 0xFF:
                        content = bytes(page.body[offset + 5:offset + 5 + slot_length])
                        alive_rows.append(Serializer.deserialize_row(content, self.columns))
                    offset += total_slot

        self.rewrite_all_rows(alive_rows)

    def rewrite_all_rows(self, rows: list):
        open(self.file_path, "wb").close()
        if os.path.exists(self.idx_path):
            os.remove(self.idx_path)
        for row in rows:
            self.append_row(row)
        self.load_all_rows()