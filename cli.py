from core.database import Database

db = Database()

# Simple command parsing functions for CREATE TABLE, INSERT INTO, and SELECT statements
def parse_create_table(command: str):
    command = command.strip().rstrip(";")

    _, _, rest = command.partition("TABLE")
    table_name, cols_part = rest.strip().split("(", 1)

    table_name = table_name.strip()
    cols_part = cols_part.strip(") ").strip()

    columns = []
    unique_columns = []

    for col_def in cols_part.split(","):
        parts = col_def.strip().split()

        col_name = parts[0]
        col_type = parts[1]

        columns.append((col_name, col_type))

        if len(parts) > 2 and parts[2].upper() == "UNIQUE":
            unique_columns.append(col_name)

    return table_name, columns, unique_columns

# Example: INSERT INTO users VALUES (1, 'Josh');
def parse_insert(command: str):
    """
    Parse an INSERT INTO command and return table name and row values.
    Example:
        INSERT INTO users VALUES (1, 'Josh');
    Returns:
        table_name: str
        row: list of values
    """
    command = command.strip().rstrip(";")
    _, _, rest = command.partition("INTO")
    table_name, values_part = rest.strip().split("VALUES", 1)
    table_name = table_name.strip()
    values_part = values_part.strip("() ").strip()
    row = []
    for val in values_part.split(","):
        val = val.strip()
        if val.startswith("'") and val.endswith("'"):
            row.append(val[1:-1])
        else:
            row.append(int(val))
    return table_name, row

# Example: SELECT name FROM users WHERE id > 1;
def parse_select(command: str):
    command = command.strip().rstrip(";")

    select_part, _, rest = command.partition("FROM")

    selected_columns = (
        select_part.replace("SELECT", "")
        .strip()
        .split(",")
    )

    selected_columns = [col.strip() for col in selected_columns]

    if "WHERE" in rest.upper():
        table_part, where_part = rest.split("WHERE", 1)
        table_name = table_part.strip()

        conditions = []

        for condition in where_part.split("AND"):
            condition = condition.strip()

            for op in ["=", ">", "<"]:
                if op in condition:
                    column, value = condition.split(op)
                    column = column.strip()
                    value = value.strip()

                    if value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    else:
                        value = int(value)

                    conditions.append((column, op, value))
                    break

        return table_name, selected_columns, conditions

    else:
        table_name = rest.strip()
        return table_name, selected_columns, []


def main():
    print("Welcome to PyBase CLI! Type 'exit' to quit.")
    while True:
        command = input("PyBase> ").strip()
        if command.lower() == "exit":
            break
        try:
            if command.upper().startswith("CREATE TABLE"):
                table_name, columns, unique_columns = parse_create_table(command)
                table = db.create_table(table_name, columns)

                for col in unique_columns:
                    table.add_unique_constraint(col)

                table.schema_manager.write(table.columns, table.unique_columns)


                print(f"Table '{table_name}' created successfully!")

            elif command.upper().startswith("INSERT INTO"):
                table_name, row = parse_insert(command)
                table = db.get_table(table_name)
                table.insert(row)
                print(f"Row inserted into '{table_name}' successfully!")

            elif command.upper().startswith("SELECT"):
                table_name, selected_columns, conditions = parse_select(command)

                table = db.get_table(table_name)

                rows = table.select_advanced(selected_columns, conditions)

                for r in rows:
                    print(r)

            else:
                print("Unsupported command.")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()