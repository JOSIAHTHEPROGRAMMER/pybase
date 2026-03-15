from core.database import Database

db = Database()


def parse_conditions(where_clause: str) -> list:
    """
    Parse a WHERE clause string into a list of condition tuples.
    Handles: =, !=, >=, <=, >, 

    Multi-char operators must be checked before single-char ones
    to avoid '>' matching the first char of '>='.

    Returns: list of (column, operator, value) tuples
    """
    conditions = []

    # Order matters - check two-char operators first
    operators = ["!=", ">=", "<=", ">", "<", "="]

    for condition in where_clause.split("AND"):
        condition = condition.strip()

        for op in operators:
            if op in condition:
                column, value = condition.split(op, 1)
                column = column.strip()
                value = value.strip()

                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                else:
                    value = int(value)

                conditions.append((column, op, value))
                break

    return conditions


# Simple command parsing functions for CREATE TABLE, INSERT INTO, and SELECT statements
def parse_create_table(command: str):
    command = command.strip().rstrip(";")

    # Use index-based split so keyword casing doesn't matter
    table_idx = command.upper().index("TABLE")
    original_rest = command[table_idx + 5:]

    table_name, cols_part = original_rest.strip().split("(", 1)
    table_name = table_name.strip()
    cols_part = cols_part.strip(") ").strip()

    columns = []
    unique_columns = []
    primary_key = None

    for col_def in cols_part.split(","):
        parts = col_def.strip().split()
        col_name = parts[0]
        col_type = parts[1].lower()  # normalize type to lowercase for schema consistency
        columns.append((col_name, col_type))

        modifiers = [p.upper() for p in parts[2:]]

        if "UNIQUE" in modifiers:
            unique_columns.append(col_name)

        # PRIMARY KEY detected - also implies UNIQUE
        if "PRIMARY" in modifiers and "KEY" in modifiers:
            if primary_key is not None:
                raise ValueError("Only one PRIMARY KEY allowed per table.")
            primary_key = col_name

    return table_name, columns, unique_columns, primary_key


# Example: DROP TABLE users;
def parse_drop_table(command: str):
    """
    Parse a DROP TABLE command and return the table name.
    """
    command = command.strip().rstrip(";")

    # Use index-based split so keyword casing doesn't matter
    table_idx = command.upper().index("TABLE")
    table_name = command[table_idx + 5:].strip()

    return table_name

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

    # Use index-based split so keyword casing doesn't matter
    into_idx = command.upper().index("INTO")
    rest = command[into_idx + 4:]

    values_idx = rest.upper().index("VALUES")
    table_name = rest[:values_idx].strip()
    values_part = rest[values_idx + 6:].strip().strip("()").strip()

    row = []
    for val in values_part.split(","):
        val = val.strip()
        if val.startswith("'") and val.endswith("'"):
            row.append(val[1:-1])
        else:
            row.append(int(val))
    return table_name, row


# Example: SELECT name FROM users WHERE id > 1 ORDER BY name ASC LIMIT 10;
def parse_select(command: str):
    """
    Parse a SELECT command and return table name, columns, conditions,
    order_by tuple, and limit value.

    Clause extraction order matters:
    LIMIT is stripped first, then ORDER BY, then WHERE - all from the tail
    of the statement to avoid consuming parts of other clauses.
    """
    command = command.strip().rstrip(";")

    # Use index-based split so keyword casing doesn't matter
    from_idx = command.upper().index("FROM")
    select_part = command[:from_idx]
    rest = command[from_idx + 4:]

    # Column names are uppercased only for * check, preserved otherwise
    selected_columns = (
        select_part.upper().replace("SELECT", "")
        .strip()
        .split(",")
    )
    selected_columns = [col.strip() for col in selected_columns]

    # Extract LIMIT first - it's always the last clause
    limit = None
    if "LIMIT" in rest.upper():
        limit_idx = rest.upper().index("LIMIT")
        limit_val = rest[limit_idx + 5:].strip()
        rest = rest[:limit_idx].strip()
        limit = int(limit_val)

    # Extract ORDER BY - comes before LIMIT, after WHERE
    order_by = None
    if "ORDER BY" in rest.upper():
        order_idx = rest.upper().index("ORDER BY")
        order_clause = rest[order_idx + 8:].strip()
        rest = rest[:order_idx].strip()

        # Parse "id ASC", "id DESC", or just "id" (defaults to ASC)
        order_parts = order_clause.split()
        order_col = order_parts[0]
        order_dir = order_parts[1].upper() if len(order_parts) > 1 else "ASC"
        order_by = (order_col, order_dir)

    # Extract WHERE conditions if present
    conditions = []
    if "WHERE" in rest.upper():
        where_idx = rest.upper().index("WHERE")
        table_name = rest[:where_idx].strip()
        where_part = rest[where_idx + 5:]
        conditions = parse_conditions(where_part)
    else:
        table_name = rest.strip()

    return table_name, selected_columns, conditions, order_by, limit


# Example: DELETE FROM users WHERE id = 1;
def parse_delete(command: str):
    """
    Parse a DELETE FROM command and return table name and conditions.
    DELETE requires a WHERE clause - no blind full-table deletes.
    """
    command = command.strip().rstrip(";")

    # Use index-based split so keyword casing doesn't matter
    from_idx = command.upper().index("FROM")
    rest = command[from_idx + 4:]

    if "WHERE" not in rest.upper():
        raise ValueError("DELETE requires a WHERE clause.")

    where_idx = rest.upper().index("WHERE")
    table_name = rest[:where_idx].strip()
    where_part = rest[where_idx + 5:]

    conditions = parse_conditions(where_part)

    return table_name, conditions


# Example: UPDATE users SET name = 'Alice2' WHERE id = 1;
def parse_update(command: str):
    """
    Parse an UPDATE command and return table name, assignments, and conditions.
    """
    command = command.strip().rstrip(";")

    # Use index-based split so keyword casing doesn't matter
    update_idx = command.upper().index("UPDATE")
    rest = command[update_idx + 6:]

    set_idx = rest.upper().index("SET")
    table_name = rest[:set_idx].strip()
    set_rest = rest[set_idx + 3:]

    if "WHERE" not in set_rest.upper():
        raise ValueError("UPDATE requires a WHERE clause.")

    where_idx = set_rest.upper().index("WHERE")
    set_part = set_rest[:where_idx]
    where_part = set_rest[where_idx + 5:]

    # Parse SET assignments: "name = 'Alice2', age = 30"
    assignments = []
    for assignment in set_part.split(","):
        col, _, value = assignment.partition("=")
        col = col.strip()
        value = value.strip()

        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        else:
            value = int(value)

        assignments.append((col, value))

    # Parse WHERE conditions (reuse same logic as SELECT/DELETE)
    conditions = parse_conditions(where_part)

    return table_name, assignments, conditions


# Example: CREATE INDEX ON users (id);
def parse_create_index(command: str):
    """
    Parse a CREATE INDEX command.
    Returns table name and column name to index.
    """
    command = command.strip().rstrip(";")

    # Use index-based split so keyword casing doesn't matter
    on_idx = command.upper().index("ON")
    rest = command[on_idx + 2:].strip()

    paren_idx = rest.index("(")
    table_name = rest[:paren_idx].strip()
    column_name = rest[paren_idx:].strip("() ").strip()

    return table_name, column_name


def main():
    print("Welcome to PyBase CLI! Type 'exit' to quit.")
    while True:
        command = input("PyBase> ").strip()
        if command.lower() == "exit":
            # Warn user if they exit with an open transaction
            if db.in_transaction():
                print("Warning: exiting with an active transaction - changes are lost.")
            break
        try:
            cmd_upper = command.upper()

            if cmd_upper in ("BEGIN", "BEGIN;"):
                db.begin_transaction()
                print("Transaction started.")

            elif cmd_upper in ("COMMIT", "COMMIT;"):
                results = db.commit_transaction()
                for r in results:
                    print(r)
                print("Transaction committed.")

            elif cmd_upper in ("ROLLBACK", "ROLLBACK;"):
                db.rollback_transaction()
                print("Transaction rolled back.")

            elif cmd_upper.startswith("CREATE INDEX"):
                table_name, column_name = parse_create_index(command)
                table = db.get_table(table_name)
                table.create_index(column_name)

            elif cmd_upper.startswith("CREATE TABLE"):
                table_name, columns, unique_columns, primary_key = parse_create_table(command)
                table = db.create_table(table_name, columns)

                for col in unique_columns:
                    table.add_unique_constraint(col)

                if primary_key:
                    table.set_primary_key(primary_key)

                print(f"Table '{table_name}' created successfully!")

            elif cmd_upper.startswith("DROP TABLE"):
                table_name = parse_drop_table(command)

                # Block drop inside an active transaction - too destructive to buffer
                if db.in_transaction():
                    raise ValueError(
                        "Cannot DROP TABLE inside a transaction. "
                        "COMMIT or ROLLBACK first."
                    )

                db.drop_table(table_name)
                print(f"Table '{table_name}' dropped successfully.")

            elif cmd_upper.startswith("INSERT INTO"):
                table_name, row = parse_insert(command)

                if db.in_transaction():
                    # Buffer operation - do not execute yet
                    db.current_transaction.add("insert", table_name, row=row)
                    print(f"Queued: INSERT into '{table_name}'.")
                else:
                    table = db.get_table(table_name)
                    table.insert(row)
                    print(f"Row inserted into '{table_name}' successfully!")

            elif cmd_upper.startswith("SELECT"):
                # SELECT always executes immediately - reads live data
                table_name, selected_columns, conditions, order_by, limit = parse_select(command)
                table = db.get_table(table_name)
                rows = table.select_advanced(selected_columns, conditions, order_by, limit)
                for r in rows:
                    print(r)

            elif cmd_upper.startswith("DELETE FROM"):
                table_name, conditions = parse_delete(command)

                if db.in_transaction():
                    # Buffer operation - do not execute yet
                    db.current_transaction.add("delete", table_name, conditions=conditions)
                    print(f"Queued: DELETE from '{table_name}'.")
                else:
                    table = db.get_table(table_name)
                    deleted_count = table.delete(conditions)
                    print(f"{deleted_count} row(s) deleted from '{table_name}'.")

            elif cmd_upper.startswith("UPDATE"):
                table_name, assignments, conditions = parse_update(command)

                if db.in_transaction():
                    # Buffer operation - do not execute yet
                    db.current_transaction.add(
                        "update", table_name,
                        assignments=assignments,
                        conditions=conditions
                    )
                    print(f"Queued: UPDATE '{table_name}'.")
                else:
                    table = db.get_table(table_name)
                    updated_count = table.update(assignments, conditions)
                    print(f"{updated_count} row(s) updated in '{table_name}'.")

            else:
                print("Unsupported command.")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
