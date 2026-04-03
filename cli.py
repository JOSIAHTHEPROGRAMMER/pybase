from core.database import Database


db = Database()


def parse_conditions(where_clause: str) -> list:
    """
    Parse a WHERE clause string into a list of condition dicts
    compatible with query.expression.Expression.evaluate.

    Handles:
        Comparison:  =, !=, <>, >, <, >=, <=
        Logical:     AND, OR
        Special:     IN, BETWEEN, LIKE, IS NULL, IS NOT NULL
        Bitwise:     &, |, ^, <<, >>

    OR splits the clause into two sides and returns a single OR condition dict.
    AND is handled by returning a list of conditions all of which must match.

    Returns a list of condition dicts.
    """
    where_clause = where_clause.strip()

    or_parts = _split_logical(where_clause, "OR")
    if len(or_parts) > 1:
        left  = parse_conditions(or_parts[0])
        right = parse_conditions(or_parts[1])
        return [{"type": "or", "left": _wrap(left), "right": _wrap(right)}]

    and_parts  = _split_logical(where_clause, "AND")
    conditions = []

    for part in and_parts:
        part = part.strip()
        conditions.append(_parse_single_condition(part))

    return conditions


def _wrap(conditions: list) -> dict:
    """
    Wrap a list of conditions into a single condition dict.
    If only one condition, return it directly.
    If multiple, chain them with AND.
    """
    if len(conditions) == 1:
        return conditions[0]

    result = conditions[0]
    for cond in conditions[1:]:
        result = {"type": "and", "left": result, "right": cond}
    return result


def _split_logical(clause: str, keyword: str) -> list:
    """
    Split a WHERE clause on a logical keyword (AND or OR) while
    respecting parentheses, quoted strings, and BETWEEN expressions.
    AND inside BETWEEN low AND high is not a logical separator.
    """
    parts   = []
    depth   = 0
    current = ""
    i       = 0
    kw_len  = len(keyword)

    while i < len(clause):
        char = clause[i]

        if char == "(":
            depth += 1
            current += char
            i += 1

        elif char == ")":
            depth -= 1
            current += char
            i += 1

        elif char in ("'", '"'):
            quote = char
            current += char
            i += 1
            while i < len(clause) and clause[i] != quote:
                current += clause[i]
                i += 1
            if i < len(clause):
                current += clause[i]
                i += 1

        elif (
            depth == 0
            and clause[i:i + kw_len].upper() == keyword
            and (i == 0 or clause[i - 1] == " ")
            and (i + kw_len >= len(clause) or clause[i + kw_len] == " ")
        ):
            if keyword == "AND" and "BETWEEN" in current.upper():
                current += clause[i:i + kw_len]
                i += kw_len
            else:
                parts.append(current.strip())
                current = ""
                i += kw_len

        else:
            current += char
            i += 1

    if current.strip():
        parts.append(current.strip())

    return parts if len(parts) > 1 else [clause]


def _parse_single_condition(part: str) -> dict:
    """
    Parse a single condition expression into a condition dict.

    Handles:
        IS NULL / IS NOT NULL
        BETWEEN low AND high
        IN (val1, val2, ...)
        LIKE pattern
        Standard comparison and bitwise operators
    """
    upper = part.upper()

    if " IS NOT NULL" in upper:
        col = part[:upper.index(" IS NOT NULL")].strip().lower()
        return {"type": "is_null", "column": col, "negated": True}

    if " IS NULL" in upper:
        col = part[:upper.index(" IS NULL")].strip().lower()
        return {"type": "is_null", "column": col, "negated": False}

    if " BETWEEN " in upper:
        idx  = upper.index(" BETWEEN ")
        col  = part[:idx].strip().lower()
        rest = part[idx + 9:].strip()

        rest_upper = rest.upper()
        if " AND " not in rest_upper:
            raise ValueError(f"BETWEEN requires AND: {part!r}")

        and_idx = rest_upper.index(" AND ")
        low     = _parse_value(rest[:and_idx].strip())
        high    = _parse_value(rest[and_idx + 5:].strip())
        return {"type": "between", "column": col, "low": low, "high": high}

    if " IN " in upper or upper.endswith(")") and " IN(" in upper.replace(" ", ""):
        in_idx = upper.index(" IN ")
        col    = part[:in_idx].strip().lower()
        rest   = part[in_idx + 4:].strip().strip("()")
        values = [_parse_value(v.strip()) for v in rest.split(",")]
        return {"type": "in", "column": col, "values": values}

    if " LIKE " in upper:
        like_idx = upper.index(" LIKE ")
        col      = part[:like_idx].strip().lower()
        pattern  = part[like_idx + 6:].strip().strip("'")
        return {"type": "like", "column": col, "pattern": pattern}

    operators = ["<>", "!=", ">=", "<=", "<<", ">>", ">", "<", "=", "&", "|", "^"]

    for op in operators:
        if op in part:
            left, _, right = part.partition(op)
            col   = left.strip().lower()
            value = _parse_value(right.strip())

            arith_ops  = ["+", "-", "*", "/", "%"]
            arithmetic = None

            for aop in arith_ops:
                if aop in col:
                    col_part, _, operand_part = col.partition(aop)
                    col        = col_part.strip()
                    arithmetic = {"op": aop, "operand": _parse_value(operand_part.strip())}
                    break

            cond = {"type": "simple", "column": col, "op": op, "value": value}
            if arithmetic:
                cond["arithmetic"] = arithmetic

            return cond

    raise ValueError(f"Cannot parse condition: {part!r}")


def _parse_value(val: str):
    """
    Convert a string token to the appropriate Python type.
    Quoted strings become str.
    TRUE/FALSE become bool.
    Numeric strings become int or float.
    """
    val = val.strip()

    if val.startswith("'") and val.endswith("'"):
        return val[1:-1]

    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    
    if val.upper() == "NULL":
        return None

    if val.upper() == "TRUE":
        return True
    if val.upper() == "FALSE":
        return False

    try:
        return int(val)
    except ValueError:
        pass

    try:
        return float(val)
    except ValueError:
        pass

    return val

def _split_column_defs(cols_part: str) -> list:
    """
    Split column definitions by comma while respecting parentheses.
    Commas inside CHECK(...) or REFERENCES(...) are not treated as separators.
    """
    defs    = []
    current = ""
    depth   = 0

    for char in cols_part:
        if char == "(":
            depth += 1
            current += char
        elif char == ")":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            defs.append(current.strip())
            current = ""
        else:
            current += char

    if current.strip():
        defs.append(current.strip())

    return defs


def parse_create_table(command: str):
    """
    Parse a CREATE TABLE command.

    Supports column modifiers:
        PRIMARY KEY
        UNIQUE
        NOT NULL
        DEFAULT <value>
        CHECK (<col> <op> <value>)
        AUTO_INCREMENT
        REFERENCES <table>(<col>)

    Returns:
        table_name, columns, unique_columns, primary_key,
        foreign_keys, not_null_columns, default_values,
        check_constraints, auto_increment_col
    """
    command = command.strip().rstrip(";")

    table_idx     = command.upper().index("TABLE")
    original_rest = command[table_idx + 5:]

    table_name, cols_part = original_rest.strip().split("(", 1)
    table_name = table_name.strip()
    cols_part  = cols_part.strip()

    # Count parens to find the actual closing paren of the table definition
    # Walk from the end and find the paren that balances the opening one
    depth = 0
    close_idx = len(cols_part) - 1
    for i in range(len(cols_part) - 1, -1, -1):
        if cols_part[i] == ")":
            depth += 1
        elif cols_part[i] == "(":
            depth -= 1
        if depth == 0:
            close_idx = i
            break

    cols_part = cols_part[:close_idx].strip()

    columns            = []
    unique_columns     = []
    primary_key        = None
    foreign_keys       = []
    not_null_columns   = []
    default_values     = {}
    check_constraints  = []
    auto_increment_col = None


   # print(f"cols_part: {repr(cols_part)}")
    for col_def in _split_column_defs(cols_part):
      #  print(f"col_def: {repr(col_def)}")

        parts    = col_def.strip().split()
        col_name = parts[0].lower()
        col_type = parts[1].lower()
        columns.append((col_name, col_type))

        upper_parts = [p.upper() for p in parts]
        modifiers   = upper_parts[2:]

        if "UNIQUE" in modifiers:
            unique_columns.append(col_name)

        if "PRIMARY" in modifiers and "KEY" in modifiers:
            if primary_key is not None:
                raise ValueError("Only one PRIMARY KEY allowed per table.")
            primary_key = col_name

        if "NOT" in modifiers and "NULL" in modifiers:
            not_null_columns.append(col_name)

        if "AUTO_INCREMENT" in modifiers:
            auto_increment_col = col_name

        if "DEFAULT" in modifiers:
            def_idx = modifiers.index("DEFAULT")
            # The default value is the token immediately after DEFAULT in parts
            raw_default = parts[def_idx + 3] if def_idx + 3 < len(parts) else None
            if raw_default is not None:
                default_values[col_name] = _parse_value(raw_default)

        # CHECK is detected from the raw col_def string because CHECK(col op val)
        # gets parsed as a single token by whitespace split and never matches modifiers
        col_def_upper = col_def.upper()
        if "CHECK" in col_def_upper:
            check_start = col_def_upper.index("CHECK")
            check_expr  = col_def[check_start:]

            paren_open  = check_expr.index("(")
            paren_close = check_expr.rindex(")")
            inner       = check_expr[paren_open + 1:paren_close].strip()

            for op in [">=", "<=", "!=", "<>", ">", "<", "="]:
                if op in inner:
                    left_side, _, right_side = inner.partition(op)
                    check_col = left_side.strip().lower()
                    check_val = _parse_value(right_side.strip())
                    check_constraints.append({
                        "column": check_col,
                        "op":     op,
                        "value":  check_val
                    })
                    break

        if "REFERENCES" in modifiers:
            ref_idx  = upper_parts.index("REFERENCES")
            ref_part = parts[ref_idx + 1]

            if "(" in ref_part and ")" in ref_part:
                ref_table = ref_part[:ref_part.index("(")].strip().lower()
                ref_col   = ref_part[ref_part.index("(") + 1:ref_part.index(")")].strip().lower()
            elif "(" in ref_part:
                ref_table = ref_part[:ref_part.index("(")].strip().lower()
                next_part = parts[ref_idx + 2] if ref_idx + 2 < len(parts) else "id"
                ref_col   = next_part.strip(")").strip().lower()
            else:
                ref_table = ref_part.strip().lower()
                ref_col   = "id"

            # Detect ON DELETE CASCADE and ON UPDATE CASCADE
            col_def_up = col_def.upper()
            on_delete  = "CASCADE" if "ON DELETE CASCADE" in col_def_up else None
            on_update  = "CASCADE" if "ON UPDATE CASCADE" in col_def_up else None

            foreign_keys.append({
                "column":     col_name,
                "ref_table":  ref_table,
                "ref_column": ref_col,
                "on_delete":  on_delete,
                "on_update":  on_update,
            })

    return (table_name, columns, unique_columns, primary_key,
            foreign_keys, not_null_columns, default_values,
            check_constraints, auto_increment_col)


def parse_drop_table(command: str):
    """
    Parse a DROP TABLE command and return the table name.
    """
    command   = command.strip().rstrip(";")
    table_idx = command.upper().index("TABLE")
    return command[table_idx + 5:].strip()


def parse_drop_database(command: str) -> bool:
    """
    Parse a DROP DATABASE command.
    Returns True if valid, raises if malformed.
    """
    command = command.strip().rstrip(";").upper()
    if command != "DROP DATABASE":
        raise ValueError("Invalid DROP DATABASE syntax. Usage: DROP DATABASE;")
    return True


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

    into_idx   = command.upper().index("INTO")
    rest       = command[into_idx + 4:]
    values_idx = rest.upper().index("VALUES")
    table_name = rest[:values_idx].strip()
    values_part = rest[values_idx + 6:].strip().strip("()").strip()

    row = []
    for val in values_part.split(","):
        val = val.strip()
        row.append(_parse_value(val))
    return table_name, row


def parse_select(command: str):
    """
    Parse a SELECT command and return table name, columns, conditions,
    order_by tuple, and limit value.

    Clause extraction order: LIMIT first, then ORDER BY, then WHERE.
    """
    command = command.strip().rstrip(";")

    from_idx     = command.upper().index("FROM")
    select_part  = command[:from_idx]
    rest         = command[from_idx + 4:]

    raw_cols = select_part[select_part.upper().index("SELECT") + 6:].strip()

    if raw_cols.strip() == "*":
        selected_columns = ["*"]
    else:
        selected_columns = [col.strip().lower() for col in raw_cols.split(",")]

    limit = None
    if "LIMIT" in rest.upper():
        limit_idx = rest.upper().index("LIMIT")
        limit_val = rest[limit_idx + 5:].strip()
        rest      = rest[:limit_idx].strip()
        limit     = int(limit_val)

    order_by = None
    if "ORDER BY" in rest.upper():
        order_idx    = rest.upper().index("ORDER BY")
        order_clause = rest[order_idx + 8:].strip()
        rest         = rest[:order_idx].strip()

        order_parts = order_clause.split()
        if order_parts:
            order_col = order_parts[0].lower()
            order_dir = order_parts[1].upper() if len(order_parts) > 1 else "ASC"
            order_by  = (order_col, order_dir)

    conditions = []
    if "WHERE" in rest.upper():
        where_idx  = rest.upper().index("WHERE")
        table_name = rest[:where_idx].strip()
        where_part = rest[where_idx + 5:]
        conditions = parse_conditions(where_part)
    else:
        table_name = rest.strip()

    return table_name, selected_columns, conditions, order_by, limit


def parse_delete(command: str):
    """
    Parse a DELETE FROM command and return table name and conditions.
    DELETE requires a WHERE clause.
    """
    command  = command.strip().rstrip(";")
    from_idx = command.upper().index("FROM")
    rest     = command[from_idx + 4:]

    if "WHERE" not in rest.upper():
        raise ValueError("DELETE requires a WHERE clause.")

    where_idx  = rest.upper().index("WHERE")
    table_name = rest[:where_idx].strip()
    where_part = rest[where_idx + 5:]
    conditions = parse_conditions(where_part)

    return table_name, conditions


def parse_update(command: str):
    """
    Parse an UPDATE command and return table name, assignments, and conditions.
    """
    command    = command.strip().rstrip(";")
    update_idx = command.upper().index("UPDATE")
    rest       = command[update_idx + 6:]

    set_idx    = rest.upper().index("SET")
    table_name = rest[:set_idx].strip()
    set_rest   = rest[set_idx + 3:]

    if "WHERE" not in set_rest.upper():
        raise ValueError("UPDATE requires a WHERE clause.")

    where_idx  = set_rest.upper().index("WHERE")
    set_part   = set_rest[:where_idx]
    where_part = set_rest[where_idx + 5:]

    assignments = []
    for assignment in set_part.split(","):
        col, _, value = assignment.partition("=")
        col   = col.strip().lower()
        value = _parse_value(value.strip())
        assignments.append((col, value))

    conditions = parse_conditions(where_part)

    return table_name, assignments, conditions


def parse_create_index(command: str):
    """
    Parse a CREATE INDEX command.
    Returns table name and column name to index.
    """
    command  = command.strip().rstrip(";")
    on_idx   = command.upper().index("ON")
    rest     = command[on_idx + 2:].strip()
    paren_idx = rest.index("(")
    table_name   = rest[:paren_idx].strip()
    column_name  = rest[paren_idx:].strip("() ").strip().lower()

    return table_name, column_name


def main():
    print("Welcome to PyBase CLI! Type 'exit' to quit.")
    while True:
        command = input("PyBase> ").strip()
        if command.lower() == "exit":
            if db.in_transaction():
                print("Warning: exiting with an active transaction - changes are lost.")
            break
        try:
            cmd_upper = command.upper()

            if cmd_upper in ("BEGIN", "BEGIN;"):
                db.begin_transaction()
                print("Transaction started.")
            

            elif cmd_upper.startswith("SAVEPOINT"):
                name = command.strip().rstrip(";")[len("SAVEPOINT"):].strip()
                if not db.in_transaction():
                    raise ValueError("No active transaction. Use BEGIN first.")
                db.current_transaction.savepoint(name)
                print(f"Savepoint '{name}' created.")

            elif cmd_upper.startswith("RELEASE SAVEPOINT"):
                name = command.strip().rstrip(";")[len("RELEASE SAVEPOINT"):].strip()
                if not db.in_transaction():
                    raise ValueError("No active transaction.")
                db.current_transaction.release_savepoint(name)
                print(f"Savepoint '{name}' released.")

            elif cmd_upper.startswith("ROLLBACK TO SAVEPOINT"):
                name = command.strip().rstrip(";")[len("ROLLBACK TO SAVEPOINT"):].strip()
                if not db.in_transaction():
                    raise ValueError("No active transaction.")
                db.current_transaction.rollback_to_savepoint(name)
                print(f"Rolled back to savepoint '{name}'.")


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
                print(table.create_index(column_name))

            elif cmd_upper.startswith("CREATE TABLE"):
                (table_name, columns, unique_columns, primary_key,
                 foreign_keys, not_null_columns, default_values,
                 check_constraints, auto_increment_col) = parse_create_table(command)

                table = db.create_table(table_name, columns)

                for col in unique_columns:
                    table.add_unique_constraint(col)

                if primary_key:
                    table.set_primary_key(primary_key)

                for col in not_null_columns:
                    table.add_not_null_constraint(col)

                for col, val in default_values.items():
                    table.set_default_value(col, val)

                for cc in check_constraints:
                    table.add_check_constraint(cc["column"], cc["op"], cc["value"])

                for fk in foreign_keys:
                    table.add_foreign_key(
                        fk["column"],
                        fk["ref_table"],
                        fk["ref_column"],
                        on_delete=fk.get("on_delete"),
                        on_update=fk.get("on_update")
                    )

                if auto_increment_col:
                    table.set_auto_increment(auto_increment_col)

                print(f"Table '{table_name}' created successfully!")

            elif cmd_upper.startswith("DROP DATABASE"):
                parse_drop_database(command)

                if db.in_transaction():
                    raise ValueError(
                        "Cannot DROP DATABASE inside a transaction. "
                        "COMMIT or ROLLBACK first."
                    )

                confirm = input(
                    "WARNING: This will delete ALL tables and data permanently. "
                    "Type YES to confirm: "
                ).strip()

                if confirm != "YES":
                    print("DROP DATABASE cancelled.")
                else:
                    db.drop_database()
                    print("Database dropped. All tables and data have been deleted.")

            elif cmd_upper.startswith("DROP TABLE"):
                table_name = parse_drop_table(command)

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
                    db.current_transaction.add("insert", table_name, row=row)
                    print(f"Queued: INSERT into '{table_name}'.")
                else:
                    table = db.get_table(table_name)
                    table.insert(row, db=db)
                    print(f"Row inserted into '{table_name}' successfully!")

            elif cmd_upper.startswith("SELECT"):
                table_name, selected_columns, conditions, order_by, limit = parse_select(command)
                table = db.get_table(table_name)
                rows  = table.select_advanced(selected_columns, conditions, order_by, limit)
                for r in rows:
                    print(r)

            elif cmd_upper.startswith("DELETE FROM"):
                table_name, conditions = parse_delete(command)

                if db.in_transaction():
                    db.current_transaction.add("delete", table_name, conditions=conditions)
                    print(f"Queued: DELETE from '{table_name}'.")
                else:
                    table         = db.get_table(table_name)
                    deleted_count = table.delete(conditions, db=db)

                    print(f"{deleted_count} row(s) deleted from '{table_name}'.")

            elif cmd_upper.startswith("UPDATE"):
                table_name, assignments, conditions = parse_update(command)

                if db.in_transaction():
                    db.current_transaction.add(
                        "update", table_name,
                        assignments=assignments,
                        conditions=conditions
                    )
                    print(f"Queued: UPDATE '{table_name}'.")
                else:
                    table         = db.get_table(table_name)
                    updated_count = table.update(assignments, conditions, db=db)
                    print(f"{updated_count} row(s) updated in '{table_name}'.")

            else:
                print("Unsupported command.")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()