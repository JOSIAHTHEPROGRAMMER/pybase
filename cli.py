from core.database import Database
from query.planner import QueryPlanner
from query.executor import QueryExecutor
from query.utils import _has_aggregate
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

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

            # split right table and ON clause
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

                # parse table aliases
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

                # parse ON left_col = right_col
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
    # parses ALTER TABLE name ADD/DROP/RENAME COLUMN ...
    command = command.strip().rstrip(";")
    upper   = command.upper()

    table_idx  = upper.index("TABLE")
    rest       = command[table_idx + 5:].strip()

    if "ADD COLUMN" in upper:
        add_idx    = upper.index("ADD COLUMN")
        table_name = command[table_idx + 5:add_idx - (table_idx + 5 - table_idx + 5)].strip()
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
    # strip EXPLAIN keyword and return the inner SELECT
    command = command.strip().rstrip(";")
    upper   = command.upper()
    if not upper.startswith("EXPLAIN"):
        raise ValueError("EXPLAIN must be followed by a SELECT statement.")
    return command[7:].strip()




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
                set_op = _detect_set_operator(command)
                alias_map = {}

                if set_op:
                    operator, left_sql, right_sql = set_op

                    def exec_side(s):
                        t, sc, c, o, l, d, g, h, j, am = parse_select(s)
                        if t in db.views:
                            t, sc, c, o, l, d, g, h, j, am = parse_select(db.views[t])
                        resolve_subqueries(c, db)
                        if j:
                            plan = QueryPlanner.build(j, sc, c, o, l, d)
                            rows, _, _ = QueryExecutor(db).execute(plan)
                            return rows
                        return db.get_table(t).select_aggregate(sc, c, g, h) if (g or _has_aggregate(sc)) else db.get_table(t).select_advanced(sc, c, o, l, distinct=d)
                
                
                    left_rows  = exec_side(left_sql)
                    right_rows = exec_side(right_sql)

                    if operator == "UNION ALL":
                        rows = left_rows + right_rows
                    elif operator == "UNION":
                        seen, rows = [], []
                        for row in left_rows + right_rows:
                            if row not in seen:
                                seen.append(row); rows.append(row)
                    elif operator == "INTERSECT":
                        seen, rows = [], []
                        for row in left_rows:
                            if row in right_rows and row not in seen:
                                seen.append(row); rows.append(row)
                    elif operator == "EXCEPT":
                        seen, rows = [], []
                        for row in left_rows:
                            if row not in right_rows and row not in seen:
                                seen.append(row); rows.append(row)
                    else:
                        rows = left_rows

                else:
                    (table_name, selected_columns, conditions, order_by,
                     limit, distinct, group_by, having, join, alias_map) = parse_select(command)
                    resolve_subqueries(conditions, db)

                    if table_name in db.views:
                        (table_name, selected_columns, conditions, order_by,
                        limit, distinct, group_by, having, join, alias_map) = parse_select(db.views[table_name])
                        resolve_subqueries(conditions, db)

                    if join:
                        plan = QueryPlanner.build(join, selected_columns, conditions, order_by, limit, distinct)
                        rows, col_names, _ = QueryExecutor(db).execute(plan)
                  
                    elif group_by or _has_aggregate(selected_columns):
                    
                        rows = db.get_table(table_name).select_aggregate(selected_columns, conditions, group_by, having)
                    else:
                        rows = db.get_table(table_name).select_advanced(selected_columns, conditions, order_by, limit, distinct=distinct)

                # print aliased column headers when aliases are present
                if alias_map and not set_op and not join:
                    headers = [alias_map.get(col, col) for col in selected_columns]
                    print(headers)

                for r in rows:
                    print(r)
                    print(type(r[0]))

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


            elif cmd_upper.startswith("EXPLAIN"):
                inner_sql = parse_explain(command)
                table_name, selected_columns, conditions, order_by, limit, distinct, group_by, having, join, alias_map = parse_select(inner_sql)
                table = db.get_table(table_name)
                print(table.explain(selected_columns, conditions, order_by, group_by, join, alias_map))

            elif cmd_upper.startswith("ALTER TABLE"):
                action, table_name, col_a, col_b, extra = parse_alter_table(command)
                table = db.get_table(table_name)
                if action == "add":
                    table.alter_add_column(col_a, col_b, default=extra)
                    print(f"Column '{col_a}' added to '{table_name}'.")
                elif action == "drop":
                    table.alter_drop_column(col_a)
                    print(f"Column '{col_a}' dropped from '{table_name}'.")
                elif action == "rename":
                    table.alter_rename_column(col_a, col_b)
                    print(f"Column '{col_a}' renamed to '{col_b}' in '{table_name}'.")

            elif cmd_upper.startswith("TRUNCATE"):
                table_name = parse_truncate(command)
                db.get_table(table_name).truncate()
                print(f"Table '{table_name}' truncated.")

            elif cmd_upper.startswith("RENAME TABLE"):
                old_name, new_name = parse_rename_table(command)
                db.rename_table(old_name, new_name)
                print(f"Table '{old_name}' renamed to '{new_name}'.")

            elif cmd_upper.startswith("CREATE VIEW") or cmd_upper.startswith("CREATE OR REPLACE VIEW"):

                view_name, select_sql, replace = parse_create_view(command)
                db.create_view(view_name, select_sql, replace)
                print(f"View '{view_name}' created.")

            elif cmd_upper.startswith("DROP VIEW"):
                view_name = parse_drop_view(command)
                db.drop_view(view_name)
                print(f"View '{view_name}' dropped.")


            else:
                print("Unsupported command.")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()