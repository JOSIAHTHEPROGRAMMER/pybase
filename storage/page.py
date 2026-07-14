import zlib



PAGE_SIZE        = 16384
PAGE_HEADER_SIZE = 16
PAGE_BODY_SIZE   = PAGE_SIZE - PAGE_HEADER_SIZE

PAGE_TYPE_DATA     = 0x01
PAGE_TYPE_OVERFLOW = 0x02

# 4 bytes at the end of a non-final overflow chunk pointing to the next page
OVERFLOW_PTR_SIZE  = 4
# sentinel value meaning no further overflow page follows
OVERFLOW_NO_NEXT   = 0xFFFFFFFF


class Page:
    """
    Represents one 16KB page in memory as a bytearray.
    All reads and writes go through this class.
    File I/O lives in Pager, not here.

    Header layout (16 bytes):
        [0:4]   page number         4 byte unsigned int
        [4:6]   row count           2 byte unsigned int
        [6:8]   free space offset   2 byte unsigned int, bytes used in body so far
        [8:12]  CRC32 checksum      4 byte unsigned int, checksum of body bytes
        [12:13] page type           1 byte, 0x01 data, 0x02 overflow
        [13:16] reserved            3 bytes, zeroed
    """

    def __init__(self, page_number: int, page_type: int = PAGE_TYPE_DATA):
        self.page_number = page_number
        self.page_type   = page_type
        # body is the usable region after the header
        self.body        = bytearray(PAGE_BODY_SIZE)
        self.row_count   = 0
        # free_offset tracks how many bytes of body have been used
        self.free_offset = 0

    @staticmethod
    def from_bytes(data: bytes) -> "Page":
        """
        Parse a raw 16KB bytes object into a Page instance.
        Verifies the CRC32 checksum of the body and raises if it does not match.
        Called by Pager.read_page after reading from disk.
        """
        if len(data) != PAGE_SIZE:
            raise ValueError(
                f"Expected {PAGE_SIZE} bytes for a page, got {len(data)}."
            )

        page_number  = int.from_bytes(data[0:4],   byteorder="big")
        row_count    = int.from_bytes(data[4:6],   byteorder="big")
        free_offset  = int.from_bytes(data[6:8],   byteorder="big")
        stored_crc   = int.from_bytes(data[8:12],  byteorder="big")
        page_type    = data[12]

        body = bytearray(data[PAGE_HEADER_SIZE:])

        # verify checksum against the body bytes
        actual_crc = zlib.crc32(bytes(body)) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            raise ValueError(
                f"Page {page_number} checksum mismatch: "
                f"expected {stored_crc:#010x}, got {actual_crc:#010x}."
            )

        page             = Page(page_number, page_type)
        page.body        = body
        page.row_count   = row_count
        page.free_offset = free_offset
        return page

    def to_bytes(self) -> bytes:
        """
        Serialize this page to exactly 16KB bytes, ready to write to disk.
        Recomputes the CRC32 checksum over the current body before serializing.
        Called by Pager.write_page before writing to disk.
        """
        checksum = zlib.crc32(bytes(self.body)) & 0xFFFFFFFF

        header = (
            self.page_number.to_bytes(4, byteorder="big") +
            self.row_count.to_bytes(2,   byteorder="big") +
            self.free_offset.to_bytes(2, byteorder="big") +
            checksum.to_bytes(4,         byteorder="big") +
            bytes([self.page_type]) +
            bytes(3)  # reserved
        )

        return header + bytes(self.body)

    def free_space(self) -> int:
        # how many bytes are still available in the body
        return PAGE_BODY_SIZE - self.free_offset

    def write_slot(self, data: bytes) -> int:
        """
        Write a blob of bytes into the next available slot in the body.
        Returns the slot offset (position within the body where data starts).
        Raises if there is not enough free space.
        """
        if len(data) > self.free_space():
            raise ValueError(
                f"Not enough space on page {self.page_number}: "
                f"need {len(data)} bytes, have {self.free_space()}."
            )

        slot_offset = self.free_offset
        self.body[slot_offset:slot_offset + len(data)] = data
        self.free_offset += len(data)
        self.row_count   += 1
        return slot_offset

    def read_slot(self, slot_offset: int, length: int) -> bytes:
        """
        Read length bytes from the body starting at slot_offset.
        Used by Pager.load_all_rows to read individual row chunks.
        """
        return bytes(self.body[slot_offset:slot_offset + length])

    def write_tombstone(self, slot_offset: int):
        """
        Overwrite the first byte at slot_offset with 0xFF.
        The tombstone byte is always the first byte of a row slot,
        same as in the flat file format.
        """
        self.body[slot_offset] = 0xFF

    def is_tombstoned(self, slot_offset: int) -> bool:
        # check if the row at this slot has been deleted
        return self.body[slot_offset] == 0xFF

    def write_overflow_ptr(self, next_page_number: int):
        """
        Append a 4 byte overflow pointer to the current free_offset.
        Written at the end of a partial row chunk to point to the next
        overflow page. Does not increment row_count since this is not
        a new row, it is a continuation pointer.
        """
        ptr = next_page_number.to_bytes(4, byteorder="big")
        self.body[self.free_offset:self.free_offset + 4] = ptr
        self.free_offset += 4

    def read_overflow_ptr(self, offset: int) -> int:
        # read the 4 byte overflow pointer stored at offset in the body
        return int.from_bytes(self.body[offset:offset + 4], byteorder="big")