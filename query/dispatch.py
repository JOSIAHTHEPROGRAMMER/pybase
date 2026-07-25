from query.sql_parser import (
    parse_create_table, parse_drop_table, parse_drop_database,
    parse_insert, parse_select, parse_delete, parse_update,
    parse_create_index, resolve_subqueries, parse_alter_table,
    parse_truncate, parse_compact_table, parse_rename_table,
    parse_create_view, parse_drop_view, parse_explain,
    parse_create_type, parse_drop_type, resolve_custom_type_columns,
    parse_create_procedure, parse_drop_procedure, parse_call,
    _detect_set_operator
)
from query.planner import QueryPlanner
from query.executor import QueryExecutor
from query.utils import _has_aggregate


def _no_op_confirm(title, text, informative):
    return True



def _substitute_params(statement: str, params: list, args: list) -> str:
    """
    Replace each parameter name in a stored procedure statement with its
    literal argument value. Numeric and boolean args are inserted as-is,
    string args are wrapped in single quotes, NULL passes through as NULL.
    Longer parameter names are substituted first so a shorter name that is
    a prefix of a longer one cannot partially match inside it.
    """
    ordered = sorted(zip(params, args), key=lambda p: len(p[0][0]), reverse=True)

    for (param_name, _), value in ordered:
        if value is None:
            literal = "NULL"
        elif isinstance(value, bool):
            literal = "TRUE" if value else "FALSE"
        elif isinstance(value, (int, float)):
            literal = str(value)
        else:
            literal = "'" + str(value).replace("'", "''") + "'"

        statement = statement.replace(param_name, literal)

    return statement


def _select_rows_and_columns(sql: str, db):
    """
    Parse and run a single SELECT statement, resolving views, subqueries,
    joins, and group by/aggregate as needed. Returns (rows, col_names).
    """
    t, sc, c, o, l, d, g, h, j, am = parse_select(sql)

    if t in db.views:
        t, sc, c, o, l, d, g, h, j, am = parse_select(db.views[t])

    resolve_subqueries(c, db)

    if j:
        plan = QueryPlanner.build(j, sc, c, o, l, d)
        rows, col_names, _ = QueryExecutor(db).execute(plan)
        return rows, col_names

    table = db.get_table(t)

    if g or _has_aggregate(sc):
        rows = table.select_aggregate(sc, c, g, h)
    else:
        rows = table.select_advanced(sc, c, o, l, distinct=d)

    if sc == ["*"]:
        col_names = [col[0] for col in table.columns]
    else:
        col_names = [am.get(col, col) for col in sc]

    return rows, col_names


def _execute_set_operation(set_op, db):
    operator, left_sql, right_sql = set_op

    left_rows,  col_names = _select_rows_and_columns(left_sql, db)
    right_rows, _         = _select_rows_and_columns(right_sql, db)

    if operator == "UNION ALL":
        result = left_rows + right_rows
    elif operator == "UNION":
        seen, result = [], []
        for row in left_rows + right_rows:
            if row not in seen:
                seen.append(row)
                result.append(row)
    elif operator == "INTERSECT":
        seen, result = [], []
        for row in left_rows:
            if row in right_rows and row not in seen:
                seen.append(row)
                result.append(row)
    elif operator == "EXCEPT":
        seen, result = [], []
        for row in left_rows:
            if row not in right_rows and row not in seen:
                seen.append(row)
                result.append(row)
    else:
        result = left_rows

    return result, col_names


def execute_statement(command: str, db, on_result, confirm=None,
                       on_schema_change=None, on_transaction_change=None,
                       on_explain=None):
    """
    Parse and execute a single SQL statement against db.

    on_result(col_names, rows, message) is called exactly once per statement
    with the outcome, success or error.

    confirm(title, text, informative) -> bool is called before any
    destructive operation (DROP TABLE, DROP DATABASE). Defaults to
    always confirming true if the caller does not supply one.

    on_schema_change(), on_transaction_change(), and on_explain(plan_text)
    are optional hooks for callers that need to react to those events,
    such as refreshing a GUI panel. They default to no-ops.

    Returns True on success, False if an error occurred.
    """
    confirm = confirm or _no_op_confirm
    on_schema_change = on_schema_change or (lambda: None)
    on_transaction_change = on_transaction_change or (lambda: None)
    on_explain = on_explain or (lambda plan_text: None)

    command   = command.strip().rstrip(";")
    cmd_upper = command.upper()

    try:
        if cmd_upper == "BEGIN":
            db.begin_transaction()
            on_transaction_change()
            on_result([], [], "Transaction started.")

        elif cmd_upper == "COMMIT":
            results = db.commit_transaction()
            on_transaction_change()
            on_result([], [], "Transaction committed.\n" + "\n".join(results))

        # SAVEPOINT branches must appear before the plain ROLLBACK check
        # because "ROLLBACK TO SAVEPOINT" starts with "ROLLBACK"
        elif cmd_upper.startswith("ROLLBACK TO SAVEPOINT"):
            name = command.strip().split()[-1]
            db.current_transaction.rollback_to_savepoint(name)
            on_result([], [], f"Rolled back to savepoint '{name}'.")

        elif cmd_upper.startswith("RELEASE SAVEPOINT"):
            name = command.strip().split()[-1]
            db.current_transaction.release_savepoint(name)
            on_result([], [], f"Savepoint '{name}' released.")

        elif cmd_upper.startswith("SAVEPOINT"):
            name = command.strip().split()[-1]
            db.current_transaction.savepoint(name)
            on_result([], [], f"Savepoint '{name}' created.")

        elif cmd_upper == "ROLLBACK":
            db.rollback_transaction()
            on_transaction_change()
            on_result([], [], "Transaction rolled back.")

        elif cmd_upper.startswith("CREATE HASH INDEX"):
            table_name, column_name = parse_create_index(command)
            table = db.get_table(table_name)
            if isinstance(column_name, list):
                raise ValueError("Hash index does not support multiple columns.")
            msg = table.create_hash_index(column_name)
            on_schema_change()
            on_result([], [], msg)

        elif cmd_upper.startswith("CREATE INDEX"):
            table_name, column_name = parse_create_index(command)
            table = db.get_table(table_name)
            if isinstance(column_name, list):
                msg = table.create_composite_index(column_name)
            else:
                msg = table.create_index(column_name)
            on_schema_change()
            on_result([], [], msg)

        elif cmd_upper.startswith("CREATE TABLE"):
            (table_name, columns, unique_columns, primary_key,
             foreign_keys, not_null_columns, default_values,
             check_constraints, auto_increment_col) = parse_create_table(command)

            columns, custom_type_map = resolve_custom_type_columns(columns, db)
            table = db.create_table(table_name, columns)

            for col_name, type_name in custom_type_map.items():
                table.register_custom_type_column(col_name, type_name)

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
                    fk["column"], fk["ref_table"], fk["ref_column"],
                    on_delete=fk.get("on_delete"), on_update=fk.get("on_update")
                )

            if auto_increment_col:
                table.set_auto_increment(auto_increment_col)

            on_schema_change()
            on_result([], [], f"Table '{table_name}' created successfully.")

        elif cmd_upper.startswith("CREATE TYPE"):
          
            type_name, fields = parse_create_type(command)
            db.create_type(type_name, fields)
            on_schema_change()
            on_result([], [], f"Type '{type_name}' created.")

        elif cmd_upper.startswith("DROP TYPE"):
            type_name = parse_drop_type(command)
            db.drop_type(type_name)
            on_schema_change()
            on_result([], [], f"Type '{type_name}' dropped.")

        elif cmd_upper.startswith("DROP DATABASE"):
            parse_drop_database(command)

            if db.in_transaction():
                raise ValueError(
                    "Cannot DROP DATABASE inside a transaction. "
                    "COMMIT or ROLLBACK first."
                )

            if not confirm(
                "Confirm DROP DATABASE",
                "Drop the entire database?",
                "This will permanently delete ALL tables, ALL data, and query history. "
                "This cannot be undone."
            ):
                on_result([], [], "DROP DATABASE cancelled.")
                return True

            db.drop_database()
            on_schema_change()
            on_result([], [], "Database dropped. All tables and data have been deleted.")

        elif cmd_upper.startswith("DROP TABLE"):
            table_name = parse_drop_table(command)

            if db.in_transaction():
                raise ValueError(
                    "Cannot DROP TABLE inside a transaction. "
                    "COMMIT or ROLLBACK first."
                )

            if not confirm(
                "Confirm DROP TABLE",
                f"Drop table '{table_name}'?",
                "This will permanently delete the table and all its data. "
                "This cannot be undone."
            ):
                on_result([], [], "DROP TABLE cancelled.")
                return True

            db.drop_table(table_name)
            on_schema_change()
            on_result([], [], f"Table '{table_name}' dropped.")

        elif cmd_upper.startswith("INSERT INTO"):
            table_name, row = parse_insert(command)

            if db.in_transaction():
                db.current_transaction.add("insert", table_name, row=row)
                on_result([], [], f"Queued: INSERT into '{table_name}'.")
            else:
                db.get_table(table_name).insert(row, db=db)
                on_result([], [], f"Row inserted into '{table_name}' successfully!")

        elif cmd_upper.startswith("SELECT"):
            set_op = _detect_set_operator(command)

            if set_op:
                rows, col_names = _execute_set_operation(set_op, db)
            else:
                rows, col_names = _select_rows_and_columns(command, db)

            on_result(col_names, rows, f"{len(rows)} row(s) returned.")

        elif cmd_upper.startswith("DELETE FROM"):
            table_name, conditions = parse_delete(command)

            if db.in_transaction():
                db.current_transaction.add("delete", table_name, conditions=conditions)
                on_result([], [], f"Queued: DELETE from '{table_name}'.")
            else:
                count = db.get_table(table_name).delete(conditions, db=db)
                on_result([], [], f"{count} row(s) deleted from '{table_name}'.")

        elif cmd_upper.startswith("UPDATE"):
            table_name, assignments, conditions = parse_update(command)

            if db.in_transaction():
                db.current_transaction.add(
                    "update", table_name,
                    assignments=assignments, conditions=conditions
                )
                on_result([], [], f"Queued: UPDATE '{table_name}'.")
            else:
                count = db.get_table(table_name).update(assignments, conditions, db=db)
                on_result([], [], f"{count} row(s) updated in '{table_name}'.")

        elif cmd_upper.startswith("EXPLAIN"):
            inner_sql = parse_explain(command)
            (table_name, selected_columns, conditions, order_by,
             limit, distinct, group_by, having, join, alias_map) = parse_select(inner_sql)
            table = db.get_table(table_name)
            result = table.explain(selected_columns, conditions, order_by, group_by, join, alias_map)
            on_explain(result)
            on_result([], [], "Query plan generated.")

        elif cmd_upper.startswith("ALTER TABLE"):
            action, table_name, col_a, col_b, extra = parse_alter_table(command)
            table = db.get_table(table_name)

            if action == "add":
                stored_type = col_b
                if db.has_custom_type(col_b):
                    stored_type = "json"
                table.alter_add_column(col_a, stored_type, default=extra)
                if db.has_custom_type(col_b):
                    table.register_custom_type_column(col_a, col_b)
                on_schema_change()
                on_result([], [], f"Column '{col_a}' added to '{table_name}'.")

            elif action == "drop":
                table.alter_drop_column(col_a)
                on_schema_change()
                on_result([], [], f"Column '{col_a}' dropped from '{table_name}'.")

            elif action == "rename":
                table.alter_rename_column(col_a, col_b)
                on_schema_change()
                on_result([], [], f"Column '{col_a}' renamed to '{col_b}' in '{table_name}'.")

        elif cmd_upper.startswith("TRUNCATE"):
            table_name = parse_truncate(command)
            db.get_table(table_name).truncate()
            on_schema_change()
            on_result([], [], f"Table '{table_name}' truncated.")

        elif cmd_upper.startswith("COMPACT TABLE"):
            table_name = parse_compact_table(command)
            db.get_table(table_name).compact()
            on_result([], [], f"Table '{table_name}' compacted.")

        elif cmd_upper.startswith("RENAME TABLE"):
            old_name, new_name = parse_rename_table(command)
            db.rename_table(old_name, new_name)
            on_schema_change()
            on_result([], [], f"Table '{old_name}' renamed to '{new_name}'.")

        elif cmd_upper.startswith("CREATE VIEW") or cmd_upper.startswith("CREATE OR REPLACE VIEW"):
            view_name, select_sql, replace = parse_create_view(command)
            db.create_view(view_name, select_sql, replace)
            on_schema_change()
            on_result([], [], f"View '{view_name}' created.")

        elif cmd_upper.startswith("DROP VIEW"):
            view_name = parse_drop_view(command)
            db.drop_view(view_name)
            on_schema_change()
            on_result([], [], f"View '{view_name}' dropped.")


        elif cmd_upper.startswith("CREATE PROCEDURE"):
            proc_name, params, body = parse_create_procedure(command)
            db.create_procedure(proc_name, params, body)
            on_schema_change()
            on_result([], [], f"Procedure '{proc_name}' created.")

        elif cmd_upper.startswith("DROP PROCEDURE"):
            proc_name = parse_drop_procedure(command)
            db.drop_procedure(proc_name)
            on_schema_change()
            on_result([], [], f"Procedure '{proc_name}' dropped.")

        elif cmd_upper.startswith("CALL"):
            proc_name, args = parse_call(command)
            procedure = db.get_procedure(proc_name)
            params = procedure["params"]

            if len(args) != len(params):
                raise ValueError(
                    f"Procedure '{proc_name}' expects {len(params)} argument(s), got {len(args)}."
                )

            executed = 0
            for stmt in procedure["body"]:
                resolved_stmt = _substitute_params(stmt, params, args)
                success = execute_statement(
                    resolved_stmt, db,
                    on_result=lambda *a: None,
                    confirm=confirm,
                    on_schema_change=on_schema_change,
                    on_transaction_change=on_transaction_change,
                    on_explain=on_explain,
                )
                if not success:
                    raise ValueError(f"Statement failed inside procedure '{proc_name}': {resolved_stmt}")
                executed += 1

            on_schema_change()
            on_result([], [], f"Procedure '{proc_name}' executed successfully ({executed} statement(s)).")

        else:
            on_result([], [], f"Unsupported command: {command[:40]}")

        return True

    except Exception as e:
        on_result([], [], f"Error in '{command[:40]}...': {e}")
        return False