import struct
from datetime import date, datetime, time, timedelta 
from decimal import Decimal

class Serializer:
    STRING_SIZE = 255


    @staticmethod
    def _decimal_scale(column_type: str) -> int:
       
        inner = column_type[column_type.index("(") + 1:column_type.index(")")]
        return int(inner.split(",")[1].strip())

    MONEY_SCALE = 2


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
                

                elif column_type.startswith("decimal("):
                    result += b"\x00" + b"\x00" * 8

                elif column_type == "money":
                    result += b"\x00" + b"\x00" * 8

                elif column_type == "date":
                    result += b"\x00" + b"\x00" * 4
                elif column_type in ("datetime", "timestamp"):
                    result += b"\x00" + b"\x00" * 8
                elif column_type == "time":
                    result += b"\x00" + b"\x00" * 4

                elif column_type in ("text", "json", "xml"):
                    result += b"\x00" + (0).to_bytes(4, byteorder="big")

                elif column_type == "blob":
                    result += b"\x00" + (0).to_bytes(4, byteorder="big")
               
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


    
            elif column_type.startswith("decimal("):
                
                scale = Serializer._decimal_scale(column_type)
                if not isinstance(value, Decimal):
                    value = Decimal(str(value))
                scaled = int((value * (10 ** scale)).quantize(Decimal("1")))
                result += scaled.to_bytes(8, byteorder="big", signed=True)

            elif column_type == "money":
                if not isinstance(value, Decimal):
                    value = Decimal(str(value))
                scaled = int((value * 100).quantize(Decimal("1")))
                result += scaled.to_bytes(8, byteorder="big", signed=True)



            elif column_type == "date":
                epoch  = date(1970, 1, 1)
                days   = (value - epoch).days
                result += days.to_bytes(4, byteorder="big", signed=True)

            elif column_type in ("datetime", "timestamp"):
                epoch   = datetime(1970, 1, 1)
                seconds = int((value - epoch).total_seconds())
                result += seconds.to_bytes(8, byteorder="big", signed=True)

            elif column_type == "time":
                seconds = value.hour * 3600 + value.minute * 60 + value.second
                result += seconds.to_bytes(4, byteorder="big", signed=True)

            elif column_type in ("text", "json", "xml"):
                encoded = value.encode("utf-8")
                length_prefix = len(encoded).to_bytes(4, byteorder="big")
                result += length_prefix + encoded

            elif column_type == "blob":
                if not isinstance(value, bytes):
                    raise TypeError("BLOB value must be bytes.")
                length_prefix = len(value).to_bytes(4, byteorder="big")
                result += length_prefix + value



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


                elif column_type.startswith("decimal(") or column_type == "money":
                    offset += 8
                elif column_type == "date":
                    offset += 4
                elif column_type in ("datetime", "timestamp"):
                    offset += 8
                elif column_type == "time":
                    offset += 4


                elif column_type in ("text", "json", "xml"):
                    length = int.from_bytes(data[offset:offset + 4], "big")
                    offset += 4 + length

                elif column_type == "blob":
                    length = int.from_bytes(data[offset:offset + 4], "big")
                    offset += 4 + length
                            
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



            elif column_type.startswith("decimal("):
                print(f"deserializing decimal: raw bytes offset={offset}")
                scale = Serializer._decimal_scale(column_type)
                raw = int.from_bytes(data[offset:offset + 8], byteorder="big", signed=True)
                quantizer = Decimal(10) ** -scale
                row.append((Decimal(raw) / Decimal(10 ** scale)).quantize(quantizer))
                offset += 8

            elif column_type == "money":
                print(f"deserializing money: raw bytes offset={offset}")
                raw = int.from_bytes(data[offset:offset + 8], byteorder="big", signed=True)
                row.append((Decimal(raw) / Decimal(100)).quantize(Decimal("0.01")))
                offset += 8

            elif column_type == "date":
                days  = int.from_bytes(data[offset:offset + 4], byteorder="big", signed=True)
                value = date(1970, 1, 1) + timedelta(days=days)
                row.append(value)
                offset += 4

            elif column_type in ("datetime", "timestamp"):
                seconds = int.from_bytes(data[offset:offset + 8], byteorder="big", signed=True)
                value   = datetime(1970, 1, 1) + timedelta(seconds=seconds)
                row.append(value)
                offset += 8

            elif column_type == "time":
                seconds = int.from_bytes(data[offset:offset + 4], byteorder="big", signed=True)
                row.append(time(seconds // 3600, (seconds % 3600) // 60, seconds % 60))
                offset += 4

            elif column_type in ("text", "json", "xml"):
                length = int.from_bytes(data[offset:offset + 4], "big")
                offset += 4
                value = data[offset:offset + length].decode("utf-8")
                row.append(value)
                offset += length

            elif column_type == "blob":
                length = int.from_bytes(data[offset:offset + 4], "big")
                offset += 4
                value = bytes(data[offset:offset + length])
                row.append(value)
                offset += length

 
        return row