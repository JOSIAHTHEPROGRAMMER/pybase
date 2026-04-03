import struct


class Serializer:
    STRING_SIZE = 255

    @staticmethod
    def serialize_row(row, columns):
        """
        Convert a row into bytes based on schema.

        Type storage sizes:
            int     4 bytes signed big-endian integer
            bigint  8 bytes signed big-endian integer
            float   8 bytes IEEE 754 double precision
            boolean 1 byte, 1 for True, 0 for False
            string  1 byte length prefix + 255 bytes padded UTF-8
        """
        result = b""

        for value, (_, column_type) in zip(row, columns):
            if column_type == "int":
                result += value.to_bytes(4, byteorder="big", signed=True)

            elif column_type == "bigint":
                result += value.to_bytes(8, byteorder="big", signed=True)

            elif column_type == "float":
                result += struct.pack(">d", value)

            elif column_type == "boolean":
                result += (1 if value else 0).to_bytes(1, byteorder="big")

            elif column_type == "string":
                encoded = value.encode("utf-8")

                if len(encoded) > Serializer.STRING_SIZE:
                    raise ValueError(
                        f"String exceeds max length of {Serializer.STRING_SIZE}"
                    )

                length_prefix = len(encoded).to_bytes(1, "big")
                padded = encoded.ljust(Serializer.STRING_SIZE, b"\x00")
                result += length_prefix + padded

        return result

    @staticmethod
    def deserialize_row(data, columns):
        """
        Convert bytes back into a row.

        Type storage sizes:
            int     4 bytes signed big-endian integer
            bigint  8 bytes signed big-endian integer
            float   8 bytes IEEE 754 double precision
            boolean 1 byte, nonzero is True
            string  1 byte length prefix + 255 bytes padded UTF-8
        """
        row = []
        offset = 0

        for _, column_type in columns:
            if column_type == "int":
                value = int.from_bytes(
                    data[offset:offset + 4],
                    byteorder="big",
                    signed=True
                )
                row.append(value)
                offset += 4

            elif column_type == "bigint":
                value = int.from_bytes(
                    data[offset:offset + 8],
                    byteorder="big",
                    signed=True
                )
                row.append(value)
                offset += 8

            elif column_type == "float":
                value = struct.unpack(">d", data[offset:offset + 8])[0]
                row.append(value)
                offset += 8

            elif column_type == "boolean":
                value = bool(int.from_bytes(data[offset:offset + 1], byteorder="big"))
                row.append(value)
                offset += 1

            elif column_type == "string":
                length = int.from_bytes(data[offset:offset + 1], "big")
                offset += 1
                raw = data[offset:offset + Serializer.STRING_SIZE]
                string_value = raw[:length].decode("utf-8")
                row.append(string_value)
                offset += Serializer.STRING_SIZE

        return row