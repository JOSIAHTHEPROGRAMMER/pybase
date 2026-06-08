import struct


class Serializer:
    STRING_SIZE = 255


    @staticmethod
    def _type_size(column_type: str) -> int:
        # returns the storage width in bytes for a given type string
        if column_type == "int":     return 4
        if column_type == "bigint":  return 8
        if column_type == "float":   return 8
        if column_type == "boolean": return 1
        if column_type == "string":  return 1 + Serializer.STRING_SIZE
        if column_type.startswith("varchar(") or column_type.startswith("char("):
            n = int(column_type[column_type.index("(") + 1:column_type.index(")")])
            return 1 + n  # 1 byte length prefix + n bytes
        raise ValueError(f"Unknown type '{column_type}'")

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

            if value is None:
                # null flag + zero bytes for this column width
                if column_type == "int":
                    result += b"\x00" + b"\x00" * 4
                elif column_type == "bigint":
                    result += b"\x00" + b"\x00" * 8
                elif column_type == "float":
                    result += b"\x00" + b"\x00" * 8
                elif column_type == "boolean":
                    result += b"\x00" + b"\x00" * 1
                elif column_type == "string":
                    result += b"\x00" + b"\x00" * (1 + Serializer.STRING_SIZE)
               
               
                elif column_type.startswith("varchar(") or column_type.startswith("char("):
                    n = int(column_type[column_type.index("(") + 1:column_type.index(")")])
                    result += b"\x00" + b"\x00" * (1 + n)
               
                continue

            result += b"\x01"  # not null flag



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

            elif column_type.startswith("varchar(") or column_type.startswith("char("):
                n = int(column_type[column_type.index("(") + 1:column_type.index(")")])
                encoded = value.encode("utf-8")
                if len(encoded) > n:
                    raise ValueError(f"Value exceeds max length of {n} for type '{column_type}'")
                length_prefix = len(encoded).to_bytes(1, "big")
                padded = encoded.ljust(n, b"\x00")
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
            null_flag = data[offset]
            offset += 1

            if null_flag == 0:
                # skip the column bytes and append None
                if column_type == "int":      offset += 4
                elif column_type == "bigint": offset += 8
                elif column_type == "float":  offset += 8
                elif column_type == "boolean": offset += 1
                elif column_type == "string": offset += 1 + Serializer.STRING_SIZE
               
                elif column_type.startswith("varchar(") or column_type.startswith("char("):
                    n = int(column_type[column_type.index("(") + 1:column_type.index(")")])
                    offset += 1 + n
                            
                row.append(None)
                continue           




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


            elif column_type.startswith("varchar(") or column_type.startswith("char("):
                n = int(column_type[column_type.index("(") + 1:column_type.index(")")])
                length = int.from_bytes(data[offset:offset + 1], "big")
                offset += 1
                raw = data[offset:offset + n]
                value = raw[:length].decode("utf-8")
                row.append(value)
                offset += n

        return row