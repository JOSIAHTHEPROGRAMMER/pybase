

class Serializer:
    STRING_SIZE = 255  # max characters

    @staticmethod
    def serialize_row(row, columns):
        """
        Convert a row into bytes based on schema.
        """
        result = b""

        for value, (_, column_type) in zip(row, columns):
            if column_type == "int":
                result += value.to_bytes(4, byteorder="big", signed=True)

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

            elif column_type == "string":
                length = int.from_bytes(data[offset:offset + 1], "big")
                offset += 1

                raw = data[offset:offset + Serializer.STRING_SIZE]
                string_value = raw[:length].decode("utf-8")

                row.append(string_value)
                offset += Serializer.STRING_SIZE

        return row