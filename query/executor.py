from query.expression import Expression


class QueryExecutor:
    """
    Executes a query plan produced by QueryPlanner against a Database instance.

    All join types use nested loop execution — for each row in the left table,
    scan all rows in the right table and emit combined rows that satisfy the
    ON condition. Simple, correct, and easy to follow for an educational engine.

    Supported join types:
        INNER      emit only rows where ON condition matches both sides
        LEFT       emit all left rows, pad right side with None when no match
        RIGHT      emit all right rows, pad left side with None when no match
        FULL       union of LEFT and RIGHT, no row from either side is lost
        CROSS      cartesian product, no ON condition required or used
    """

    def __init__(self, db):
        self.db = db

    def execute(self, plan: dict) -> tuple:
        """
        Execute a join plan and return (rows, column_names, column_index).

        rows is a flat list of combined rows, one per result record.
        column_names is the ordered list of 'table.column' name strings.
        column_index maps each 'table.column' name to its position in a row.
        """
        left_table_name  = plan["left_table"]
        right_table_name = plan["right_table"]
        left_alias       = plan.get("left_alias")
        right_alias      = plan.get("right_alias")
        join_type        = plan["join_type"]

        left_table  = self.db.get_table(left_table_name)
        right_table = self.db.get_table(right_table_name)

        left_prefix  = left_alias  or left_table_name
        right_prefix = right_alias or right_table_name

        # Build merged column name list and index for the combined row
        left_col_names  = [f"{left_prefix}.{col[0]}"  for col in left_table.columns]
        right_col_names = [f"{right_prefix}.{col[0]}" for col in right_table.columns]
        all_col_names   = left_col_names + right_col_names

        column_index = {name: i for i, name in enumerate(all_col_names)}

        left_width  = len(left_table.columns)
        right_width = len(right_table.columns)

        # Resolve ON column positions in the original tables
        on_left_col  = plan.get("on_left")
        on_right_col = plan.get("on_right")

        left_col_index  = left_table._build_column_index()
        right_col_index = right_table._build_column_index()

        if join_type != "CROSS":
            # Strip table/alias prefix from ON columns if present
            on_left_bare  = on_left_col.split(".")[-1]  if on_left_col  else None
            on_right_bare = on_right_col.split(".")[-1] if on_right_col else None

            if on_left_bare not in left_col_index:
                raise ValueError(
                    f"Column '{on_left_bare}' does not exist in table '{left_table_name}'."
                )
            if on_right_bare not in right_col_index:
                raise ValueError(
                    f"Column '{on_right_bare}' does not exist in table '{right_table_name}'."
                )

            on_left_idx  = left_col_index[on_left_bare]
            on_right_idx = right_col_index[on_right_bare]
        else:
            on_left_idx  = None
            on_right_idx = None

        null_left  = [None] * left_width
        null_right = [None] * right_width


    # print(f"left_width: {left_width}")
    # print(f"right_width: {right_width}")
    # print(f"null_left: {null_left}")
    # print(f"null_right: {null_right}")
    # print(f"join_type: {join_type}")
    # print(f"on_left_idx: {on_left_idx}")
    # print(f"on_right_idx: {on_right_idx}")
    # print(f"left rows sample: {left_table.rows[:2]}")
    # print(f"right rows sample: {right_table.rows[:2]}")

        if join_type == "INNER":
            joined = self._inner(
                left_table.rows, right_table.rows,
                on_left_idx, on_right_idx
            )

        elif join_type == "LEFT":
            joined = self._left(
                left_table.rows, right_table.rows,
                on_left_idx, on_right_idx, null_right
            )

        elif join_type == "RIGHT":
            joined = self._right(
                left_table.rows, right_table.rows,
                on_left_idx, on_right_idx, null_left
            )

        # print(f"right join produced {len(joined)} rows")
        # for r in joined:
            # print(f"  {r}")

        elif join_type == "FULL":
            joined = self._full(
                left_table.rows, right_table.rows,
                on_left_idx, on_right_idx, null_left, null_right
            )

        elif join_type == "CROSS":
            joined = self._cross(left_table.rows, right_table.rows)

        else:
            raise ValueError(f"Unknown join type: {join_type}")

        # Apply WHERE conditions using the merged column index
        conditions = plan.get("conditions", [])
        if conditions:
            joined = [
                row for row in joined
                if self._matches(row, conditions, column_index)
            ]

        # Apply ORDER BY
        order_by = plan.get("order_by")
        if order_by:
            for col, direction in reversed(order_by):
                order_key = self._resolve_col(col, column_index, left_prefix, right_prefix)

                if order_key not in column_index:
                    raise ValueError(f"ORDER BY column '{col}' does not exist.")

                col_idx = column_index[order_key]

                joined.sort(
                    key=lambda row: (row[col_idx] is None, row[col_idx]),
                    reverse=(direction == "DESC")
                )

        # Apply LIMIT
        limit = plan.get("limit")
        if limit is not None:
            joined = joined[:limit]

        # Apply DISTINCT
        if plan.get("distinct"):
            seen, deduped = [], []
            for row in joined:
                if row not in seen:
                    seen.append(row)
                    deduped.append(row)
            joined = deduped

        # Apply column projection
        selected_columns = plan.get("selected_columns", ["*"])
        if selected_columns == ["*"]:
            return joined, all_col_names, column_index

        projected_names = []
        for col in selected_columns:
            resolved = self._resolve_col(col, column_index, left_prefix, right_prefix)
            if resolved not in column_index:
                raise ValueError(f"Column '{col}' does not exist in join result.")
            projected_names.append(resolved)

        projected_index = {name: i for i, name in enumerate(projected_names)}

        projected_rows = [
            [row[column_index[col]] for col in projected_names]
            for row in joined
        ]

        return projected_rows, projected_names, projected_index

    def _inner(self, left_rows, right_rows, on_left_idx, on_right_idx):
        result = []
        for left_row in left_rows:
            for right_row in right_rows:
                if left_row[on_left_idx] == right_row[on_right_idx]:
                    result.append(list(left_row) + list(right_row))
        return result

    def _left(self, left_rows, right_rows, on_left_idx, on_right_idx, null_right):
        result = []
        for left_row in left_rows:
            matched = False
            for right_row in right_rows:
                if left_row[on_left_idx] == right_row[on_right_idx]:
                    result.append(list(left_row) + list(right_row))
                    matched = True
            if not matched:
                result.append(list(left_row) + null_right)
        return result

    def _right(self, left_rows, right_rows, on_left_idx, on_right_idx, null_left):
       # print(f"  _right called, null_left={null_left}, on_left_idx={on_left_idx}, on_right_idx={on_right_idx}")
        result = []
        for right_row in right_rows:
            matched = False
            for left_row in left_rows:
               # print(f"    comparing left[{on_left_idx}]={left_row[on_left_idx]} right[{on_right_idx}]={right_row[on_right_idx]}")
                if left_row[on_left_idx] == right_row[on_right_idx]:
                    result.append(list(left_row) + list(right_row))
                    matched = True
            if not matched:
                   # print(f"    null_left type: {type(null_left)}, right_row type: {type(right_row)}")
                   # print(f"    null_left: {null_left}")
                   # print(f"    right_row: {right_row}")
                    result.append(null_left + list(right_row))
        return result

    def _full(self, left_rows, right_rows, on_left_idx, on_right_idx,
              null_left, null_right):
        result        = []
        matched_right = set()

        for left_row in left_rows:
            matched = False
            for i, right_row in enumerate(right_rows):
                if left_row[on_left_idx] == right_row[on_right_idx]:
                    result.append(list(left_row) + list(right_row))
                    matched_right.add(i)
                    matched = True
            if not matched:
                result.append(list(left_row) + null_right)

        for i, right_row in enumerate(right_rows):
            if i not in matched_right:
                result.append(null_left + list(right_row))

        return result

    def _cross(self, left_rows, right_rows):
        return [
            list(left_row) + list(right_row)
            for left_row in left_rows
            for right_row in right_rows
        ]

    def _matches(self, row, conditions, column_index):
        for condition in conditions:
            if not Expression.evaluate(condition, row, column_index):
                return False
        return True

    def _resolve_col(self, col: str, column_index: dict,
                     left_prefix: str, right_prefix: str) -> str:
        """
        Resolve a bare column name or prefixed column name to the form
        used in the merged column index (table.column or alias.column).

        If col is already in the index it is returned as-is.
        If col is bare, tries left_prefix.col then right_prefix.col.
        Raises if the column cannot be resolved.
        """
        if col in column_index:
            return col

        left_candidate  = f"{left_prefix}.{col}"
        right_candidate = f"{right_prefix}.{col}"

        if left_candidate in column_index:
            return left_candidate
        if right_candidate in column_index:
            return right_candidate

        raise ValueError(
            f"Column '{col}' is ambiguous or does not exist in the join result. "
            f"Use table.column or alias.column syntax."
        )
