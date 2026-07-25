from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from query.utils import _has_aggregate


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

    if upper.startswith("EXISTS"):
        inner = part[6:].strip().strip("()")
        return {"type": "exists", "subquery": inner}

    if " IN " in upper and "SELECT" in upper:
        in_idx = upper.index(" IN ")
        col    = part[:in_idx].strip().lower()
        inner  = part[in_idx + 4:].strip().strip("()")
        return {"type": "subquery_in", "column": col, "subquery": inner}

    for qualifier in ("ANY", "ALL"):
        for op in (">=", "<=", "!=", "<>", ">", "<", "="):
            token = f"{op} {qualifier}"
            if token in upper:
                idx  = upper.index(token)
                col  = part[:idx].strip().lower()
                inner = part[idx + len(token):].strip().strip("()")
                return {
                    "type":      "any_all",
                    "column":    col,
                    "op":        op,
                    "qualifier": qualifier,
                    "subquery":  inner
                }

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
                if "(" not in col and aop in col:
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
    val = val.strip()

    if (val[:2].upper() == "X'" and val.endswith("'")) or (val[:2].upper() == "X\"" and val.endswith('"')):
        hex_str = val[2:-1]
        return bytes.fromhex(hex_str)

    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]

    if val.startswith("'") and val.endswith("'"):
        inner = val[1:-1]
        try:
            if " " in inner and len(inner) == 19:
                return datetime.strptime(inner, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        try:
            if len(inner) == 10 and inner[4] == "-":
                return date.fromisoformat(inner)
        except ValueError:
            pass
        try:
            if ":" in inner and len(inner) == 8:
                parts = inner.split(":")
                return time(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            pass
        return inner

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
    Split column definitions by comma while respecting parentheses and quotes.
    Commas inside CHECK(...), REFERENCES(...), or quoted DEFAULT values
    are not treated as separators.
    """
    defs    = []
    current = ""
    depth   = 0
    i       = 0

    while i < len(cols_part):
        char = cols_part[i]

        if char in ("'", '"'):
            quote = char
            current += char
            i += 1
            while i < len(cols_part) and cols_part[i] != quote:
                current += cols_part[i]
                i += 1
            if i < len(cols_part):
                current += cols_part[i]
                i += 1

        elif char == "(":
            depth += 1
            current += char
            i += 1

        elif char == ")":
            depth -= 1
            current += char
            i += 1

        elif char == "," and depth == 0:
            defs.append(current.strip())
            current = ""
            i += 1

        else:
            current += char
            i += 1

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

    for col_def in _split_column_defs(cols_part):
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
            col_def_upper  = col_def.upper()
            default_start  = col_def_upper.index("DEFAULT") + len("DEFAULT")
            remainder      = col_def[default_start:].strip()

            if remainder.startswith("'") or remainder.startswith('"'):
                quote       = remainder[0]
                end_idx     = remainder.index(quote, 1)
                raw_default = remainder[:end_idx + 1]
            else:
                raw_default = remainder.split()[0] if remainder.split() else None

            if raw_default is not None:
                default_values[col_name] = _parse_value(raw_default)

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
    for val in _split_values(values_part):
        val = val.strip()
        row.append(_parse_value(val))
    return table_name, row


def _split_values(values_part: str) -> list:
    """
    Split a VALUES list on commas while respecting quoted strings.
    Commas inside single or double quotes are not treated as separators.
    """
    parts   = []
    current = ""
    i       = 0

    while i < len(values_part):
        char = values_part[i]

        if char in ("'", '"'):
            quote = char
            current += char
            i += 1
            while i < len(values_part) and values_part[i] != quote:
                current += values_part[i]
                i += 1
            if i < len(values_part):
                current += values_part[i]
                i += 1

        elif char == ",":
            parts.append(current.strip())
            current = ""
            i += 1

        else:
            current += char
            i += 1

    if current.strip():
        parts.append(current.strip())

    return parts


def _detect_set_operator(command: str):
    depth = 0
    upper = command.upper()
    for op in ("UNION ALL", "UNION", "INTERSECT", "EXCEPT"):
        i = 0
        while i < len(upper):
            if upper[i] == "(": depth += 1
            elif upper[i] == ")": depth -= 1
            elif depth == 0 and upper[i:i+len(op)] == op:
                prev_ok = i == 0 or upper[i-1] == " "
                next_ok = i + len(op) >= len(upper) or upper[i+len(op)] == " "
                if prev_ok and next_ok:
                    return op, command[:i].strip(), command[i+len(op):].strip()
            i += 1
        depth = 0
    return None


def _parse_join(command: str) -> dict | None:
    upper = command.upper()
    join_types = ["FULL OUTER JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "CROSS JOIN"]

    for jt in join_types:
        if jt in upper:
            idx        = upper.index(jt)
            left_part  = command[:idx].strip()

            left_upper = left_part.upper()
            if "FROM" in left_upper:
                from_idx  = left_upper.rindex("FROM")
                left_part = left_part[from_idx + 4:].strip()

            rest       = command[idx + len(jt):].strip()
            join_type  = jt.replace(" JOIN", "").replace(" OUTER", "").strip()

            if " ON " in rest.upper():
                on_idx       = rest.upper().index(" ON ")
                right_part   = rest[:on_idx].strip()
                on_clause    = rest[on_idx + 4:].strip()

                tail = ""
                for keyword in ("WHERE", "ORDER BY", "GROUP BY", "LIMIT", "HAVING"):
                    kw_idx = on_clause.upper().find(keyword)
                    if kw_idx != -1:
                        tail      = on_clause[kw_idx:]
                        on_clause = on_clause[:kw_idx].strip()
                        break

                left_alias   = None
                right_alias  = None

                if " AS " in left_part.upper():
                    ai = left_part.upper().index(" AS ")
                    left_alias = left_part[ai + 4:].strip().lower()
                    left_part  = left_part[:ai].strip()
                elif " " in left_part.strip():
                    parts      = left_part.strip().split()
                    left_alias = parts[-1].lower()
                    left_part  = parts[0]

                if " AS " in right_part.upper():
                    ai = right_part.upper().index(" AS ")
                    right_alias = right_part[ai + 4:].strip().lower()
                    right_part  = right_part[:ai].strip()
                elif " " in right_part.strip():
                    parts       = right_part.strip().split()
                    right_alias = parts[-1].lower()
                    right_part  = parts[0]

                eq_idx    = on_clause.index("=")
                on_left   = on_clause[:eq_idx].strip().lower()
                on_right  = on_clause[eq_idx + 1:].strip().lower()

                return {
                    "join_type":   join_type,
                    "left_table":  left_part.strip().lower(),
                    "right_table": right_part.strip().lower(),
                    "left_alias":  left_alias,
                    "right_alias": right_alias,
                    "on_left":     on_left,
                    "on_right":    on_right,
                    "tail":        tail,
                }
            elif jt == "CROSS JOIN":
                return {
                    "join_type":   "CROSS",
                    "left_table":  left_part.strip().lower(),
                    "right_table": rest.strip().lower(),
                    "left_alias":  None,
                    "right_alias": None,
                    "on_left":     None,
                    "on_right":    None,
                }
    return None


def parse_select(command: str):
    """
    Parse a SELECT command and return table name, columns, conditions,
    order_by tuple, and limit value.

    Clause extraction order: LIMIT first, then ORDER BY, then WHERE.
    """
    command = command.strip().rstrip(";")
    join = _parse_join(command)

    if join:
         table_name = join["left_table"]
         rest = join.get("tail", "")

    alias_map = {}
    from_idx     = command.upper().index("FROM")
    select_part  = command[:from_idx]

    if not join:
     rest = command[from_idx + 4:]

    raw_cols = select_part[select_part.upper().index("SELECT") + 6:].strip()

    distinct = False
    if raw_cols.upper().startswith("DISTINCT"):
        distinct  = True
        raw_cols  = raw_cols[8:].strip()

    if raw_cols.strip() == "*":
        selected_columns = ["*"]
    else:
        selected_columns = []

        for col in raw_cols.split(","):
            col = col.strip()
            upper = col.upper()
            if " AS " in upper:
                idx  = upper.index(" AS ")
                name = col[:idx].strip().lower()
                alias = col[idx + 4:].strip().lower()
                selected_columns.append(name)
                alias_map[name] = alias
            else:
                selected_columns.append(col.lower())

    limit = None
    if "LIMIT" in rest.upper():
        limit_idx = rest.upper().index("LIMIT")
        limit_val = rest[limit_idx + 5:].strip()
        rest      = rest[:limit_idx].strip()
        limit     = int(limit_val)

    order_by = []
    if "ORDER BY" in rest.upper():
        order_idx    = rest.upper().index("ORDER BY")
        order_clause = rest[order_idx + 8:].strip()
        rest         = rest[:order_idx].strip()

        for part in order_clause.split(","):
            parts     = part.strip().split()
            col       = parts[0].lower()
            direction = parts[1].upper() if len(parts) > 1 else "ASC"

            for real, alias in alias_map.items():
                if col == alias:
                    col = real
                    break

            order_by.append((col, direction))

    group_by = []
    having   = []
    if "GROUP BY" in rest.upper():
        gb_idx   = rest.upper().index("GROUP BY")
        gb_clause = rest[gb_idx + 8:].strip()
        rest      = rest[:gb_idx].strip()
        if "HAVING" in gb_clause.upper():
            hav_idx   = gb_clause.upper().index("HAVING")
            having    = parse_conditions(gb_clause[hav_idx + 6:].strip())
            gb_clause = gb_clause[:hav_idx].strip()
        group_by = [c.strip().lower() for c in gb_clause.split(",")]

    conditions = []
    if "WHERE" in rest.upper():
        where_idx  = rest.upper().index("WHERE")
        where_part = rest[where_idx + 5:]
        conditions = parse_conditions(where_part)
        if not join:
            table_name = rest[:where_idx].strip()
    else:
        if not join:
            table_name = rest.strip()

    if not join and " AS " in table_name.upper():
        idx = table_name.upper().index(" AS ")
        table_name = table_name[:idx].strip()
    return table_name, selected_columns, conditions, order_by, limit, distinct, group_by, having, join, alias_map


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

    Assignments are (column, value) tuples. If the right-hand side is an
    arithmetic expression on the same column being assigned (e.g.
    salary = salary + 5000), value is instead a dict
    {"type": "arithmetic", "op": op, "operand": operand_value},
    resolved against each row's current value at update time.
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
    arith_ops   = ["+", "-", "*", "/", "%"]

    for assignment in _split_values(set_part):
        col, _, raw_value = assignment.partition("=")
        col       = col.strip().lower()
        raw_value = raw_value.strip()

        arithmetic = None

        if raw_value.lower().startswith(col + " "):
            # self-referential arithmetic, e.g. salary = salary + amount
            # resolved per row at update time against the current value
            remainder = raw_value[len(col):].strip()
            for op in arith_ops:
                if remainder.startswith(op):
                    operand_str = remainder[len(op):].strip()
                    arithmetic  = {
                        "type": "arithmetic",
                        "op": op,
                        "operand": _parse_value(operand_str)
                    }
                    break
        else:
            # literal arithmetic, e.g. salary = 50000 + 1000
            # both sides are known now, so evaluate immediately
            for op in arith_ops:
                token = f" {op} "
                if token in raw_value:
                    left_str, _, right_str = raw_value.partition(token)
                    left_val  = _parse_value(left_str.strip())
                    right_val = _parse_value(right_str.strip())
                    if isinstance(left_val, (int, float)) and isinstance(right_val, (int, float)):
                        if op == "+": raw_value = str(left_val + right_val)
                        elif op == "-": raw_value = str(left_val - right_val)
                        elif op == "*": raw_value = str(left_val * right_val)
                        elif op == "/": raw_value = str(left_val / right_val)
                        elif op == "%": raw_value = str(left_val % right_val)
                    break

        value = arithmetic if arithmetic is not None else _parse_value(raw_value)
        assignments.append((col, value))

    conditions = parse_conditions(where_part)

    return table_name, assignments, conditions


def parse_create_index(command: str):
    """
    Parse a CREATE INDEX command.
    Returns table name and column name to index.
    """
    command   = command.strip().rstrip(";")
    on_idx    = command.upper().index("ON")
    rest      = command[on_idx + 2:].strip()
    paren_idx = rest.index("(")
    table_name   = rest[:paren_idx].strip()
    cols_part    = rest[paren_idx:].strip("() ").strip()
    column_names = [c.strip().lower() for c in cols_part.split(",")]
    if len(column_names) == 1:
        return table_name, column_names[0]
    return table_name, column_names


def resolve_subqueries(conditions: list, db):
    for cond in conditions:
        ctype = cond.get("type")
        if ctype in ("and", "or"):
            resolve_subqueries([cond["left"]], db)
            resolve_subqueries([cond["right"]], db)
        elif ctype == "not":
            resolve_subqueries([cond["condition"]], db)
        elif ctype == "exists":
            t, sc, c, o, l, d, g, h, j, am = parse_select(cond["subquery"])
            table = db.get_table(t)
            rows = table.select_aggregate(sc, c, g, h) if (g or _has_aggregate(sc)) else table.select_advanced(sc, c, o, l, distinct=d)
            cond["rows"] = rows
            del cond["subquery"]
        elif ctype == "subquery_in":
            t, sc, c, o, l, d, g, h, j, am = parse_select(cond["subquery"])
            table = db.get_table(t)
            rows = table.select_aggregate(sc, c, g, h) if (g or _has_aggregate(sc)) else table.select_advanced(sc, c, o, l, distinct=d)
            cond["values"] = [row[0] if isinstance(row, list) else row for row in rows]
            cond["type"] = "in"
            del cond["subquery"]
        elif ctype == "any_all":
            t, sc, c, o, l, d, g, h, j, am = parse_select(cond["subquery"])
            table = db.get_table(t)
            rows = table.select_aggregate(sc, c, g, h) if (g or _has_aggregate(sc)) else table.select_advanced(sc, c, o, l, distinct=d)
            cond["values"] = [row[0] if isinstance(row, list) else row for row in rows]
            del cond["subquery"]


def parse_alter_table(command: str):
    command = command.strip().rstrip(";")
    upper   = command.upper()

    table_idx  = upper.index("TABLE")
    rest       = command[table_idx + 5:].strip()

    if "ADD COLUMN" in upper:
        table_name = rest[:rest.upper().index("ADD COLUMN")].strip()
        col_def    = rest[rest.upper().index("ADD COLUMN") + 10:].strip()
        parts      = col_def.split()
        col_name   = parts[0].lower()
        col_type   = parts[1].lower()
        default    = _parse_value(parts[parts[0:].index(parts[0]) + 3]) if "DEFAULT" in [p.upper() for p in parts] else None
        return "add", table_name, col_name, col_type, default

    if "DROP COLUMN" in upper:
        table_name = rest[:rest.upper().index("DROP COLUMN")].strip()
        col_name   = rest[rest.upper().index("DROP COLUMN") + 11:].strip().lower()
        return "drop", table_name, col_name, None, None

    if "RENAME COLUMN" in upper:
        table_name = rest[:rest.upper().index("RENAME COLUMN")].strip()
        rename_part = rest[rest.upper().index("RENAME COLUMN") + 13:].strip()
        if " TO " not in rename_part.upper():
            raise ValueError("RENAME COLUMN requires TO: RENAME COLUMN old TO new")
        to_idx   = rename_part.upper().index(" TO ")
        old_name = rename_part[:to_idx].strip().lower()
        new_name = rename_part[to_idx + 4:].strip().lower()
        return "rename", table_name, old_name, new_name, None

    raise ValueError(f"Unknown ALTER TABLE syntax: {command}")


def parse_truncate(command: str) -> str:
    command = command.strip().rstrip(";")
    upper   = command.upper()
    if "TABLE" not in upper:
        raise ValueError("TRUNCATE requires TABLE keyword.")
    return command[upper.index("TABLE") + 5:].strip()


def parse_compact_table(command: str) -> str:
    command = command.strip().rstrip(";")
    upper   = command.upper()
    if "TABLE" not in upper:
        raise ValueError("COMPACT TABLE requires TABLE keyword.")
    return command[upper.index("TABLE") + 5:].strip()


def parse_rename_table(command: str) -> tuple:
    command = command.strip().rstrip(";")
    upper   = command.upper()
    if "TABLE" not in upper:
        raise ValueError("RENAME TABLE requires TABLE keyword.")
    rest = command[upper.index("TABLE") + 5:].strip()
    if " TO " not in rest.upper():
        raise ValueError("RENAME TABLE requires TO: RENAME TABLE old TO new")
    to_idx   = rest.upper().index(" TO ")
    old_name = rest[:to_idx].strip()
    new_name = rest[to_idx + 4:].strip()
    return old_name, new_name


def parse_create_procedure(command: str) -> tuple:
    """
    Parse a CREATE PROCEDURE name(params) AS BEGIN ... END command.
    Returns procedure name, a list of (param_name, param_type) tuples,
    and a list of individual statement strings from the body.
    """
    command = command.strip().rstrip(";")
    upper   = command.upper()

    if "PROCEDURE" not in upper:
        raise ValueError("CREATE PROCEDURE requires PROCEDURE keyword.")
    if "BEGIN" not in upper or "END" not in upper:
        raise ValueError("CREATE PROCEDURE body must be wrapped in BEGIN and END.")

    proc_idx   = upper.index("PROCEDURE") + len("PROCEDURE")
    paren_idx  = command.index("(", proc_idx)
    proc_name  = command[proc_idx:paren_idx].strip().lower()

    close_paren = command.index(")", paren_idx)
    params_part = command[paren_idx + 1:close_paren].strip()

    params = []
    if params_part:
        for param_def in _split_column_defs(params_part):
            parts = param_def.strip().split()
            params.append((parts[0].lower(), parts[1].lower()))

    begin_idx = upper.index("BEGIN", close_paren)
    end_idx   = upper.rindex("END")
    body_part = command[begin_idx + 5:end_idx].strip()

    body = [stmt.strip() for stmt in body_part.split(";") if stmt.strip()]

    return proc_name, params, body


def parse_drop_procedure(command: str) -> str:
    command = command.strip().rstrip(";")
    upper   = command.upper()
    if "PROCEDURE" not in upper:
        raise ValueError("DROP PROCEDURE requires PROCEDURE keyword.")
    return command[upper.index("PROCEDURE") + len("PROCEDURE"):].strip().lower()


def parse_call(command: str) -> tuple:
    """
    Parse a CALL proc_name(arg1, arg2, ...) command.
    Returns procedure name and a list of parsed argument values.
    """
    command = command.strip().rstrip(";")
    upper   = command.upper()

    if not upper.startswith("CALL"):
        raise ValueError("CALL statement must start with CALL.")

    rest       = command[4:].strip()
    paren_idx  = rest.index("(")
    proc_name  = rest[:paren_idx].strip().lower()

    close_paren = rest.rindex(")")
    args_part   = rest[paren_idx + 1:close_paren].strip()

    args = [_parse_value(v.strip()) for v in _split_values(args_part)] if args_part else []

    return proc_name, args


def parse_create_view(command: str) -> tuple:
    command = command.strip().rstrip(";")
    upper   = command.upper()
    replace = "OR REPLACE" in upper
    if "VIEW" not in upper:
        raise ValueError("CREATE VIEW requires VIEW keyword.")
    if " AS " not in upper:
        raise ValueError("CREATE VIEW requires AS keyword.")
    view_start = upper.index("VIEW") + 4
    as_idx     = upper.index(" AS ")
    view_name  = command[view_start:as_idx].strip().lower()
    select_sql = command[as_idx + 4:].strip()
    return view_name, select_sql, replace


def parse_drop_view(command: str) -> str:
    command = command.strip().rstrip(";")
    upper   = command.upper()
    if "VIEW" not in upper:
        raise ValueError("DROP VIEW requires VIEW keyword.")
    return command[upper.index("VIEW") + 4:].strip().lower()


def parse_explain(command: str) -> str:
    command = command.strip().rstrip(";")
    upper   = command.upper()
    if not upper.startswith("EXPLAIN"):
        raise ValueError("EXPLAIN must be followed by a SELECT statement.")
    return command[7:].strip()


def parse_create_type(command: str) -> tuple:
    """
    Parse a CREATE TYPE ... AS (...) command.
    Returns type name and a list of (field_name, field_type) tuples.
    """
    command = command.strip().rstrip(";")
    upper   = command.upper()

    if "TYPE" not in upper:
        raise ValueError("CREATE TYPE requires TYPE keyword.")
    if " AS " not in upper:
        raise ValueError("CREATE TYPE requires AS keyword.")

    type_idx  = upper.index("TYPE") + 4
    as_idx    = upper.index(" AS ")
    type_name = command[type_idx:as_idx].strip().lower()

    rest = command[as_idx + 4:].strip()
    if not (rest.startswith("(") and rest.endswith(")")):
        raise ValueError("CREATE TYPE fields must be wrapped in parentheses.")

    fields_part = rest[1:-1].strip()
    fields = []

    for field_def in _split_column_defs(fields_part):
        parts = field_def.strip().split()
        fields.append((parts[0].lower(), parts[1].lower()))

    return type_name, fields


def parse_drop_type(command: str) -> str:
    command = command.strip().rstrip(";")
    upper   = command.upper()
    if "TYPE" not in upper:
        raise ValueError("DROP TYPE requires TYPE keyword.")
    return command[upper.index("TYPE") + 4:].strip().lower()


def resolve_custom_type_columns(columns: list, db) -> tuple:
    """
    Given a raw column list from parse_create_table, replace any column
    whose declared type is a registered custom type with json for storage,
    and return a side dict of {column_name: type_name} for those columns.
    """
    resolved   = []
    custom_map = {}

    for col_name, col_type in columns:
        base = col_type.split("(")[0]
        if db.has_custom_type(base):
            custom_map[col_name] = base
            resolved.append((col_name, "json"))
        else:
            resolved.append((col_name, col_type))

    return resolved, custom_map