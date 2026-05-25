class QueryPlanner:
    """
    Builds a query plan from a parsed SELECT statement that contains a JOIN.

    The plan is a plain dict consumed by QueryExecutor. The planner does no
    execution and touches no data. Its only job is to validate that the join
    descriptor is well-formed and package it into a structure the executor
    can walk without re-parsing anything.

    Supported join types:
        INNER JOIN
        LEFT JOIN
        RIGHT JOIN
        FULL OUTER JOIN
        CROSS JOIN
        SELF JOIN (an INNER JOIN where both sides reference the same table)

    Plan dict structure:
        {
            "join_type":        str,   one of INNER, LEFT, RIGHT, FULL, CROSS
            "left_table":       str,   name of the left table
            "right_table":      str,   name of the right table
            "left_alias":       str or None
            "right_alias":      str or None
            "on_left":          str or None,  column on the left side of ON
            "on_right":         str or None,  column on the right side of ON
            "selected_columns": list,  ["*"] or list of "table.col" or "col" strings
            "conditions":       list,  WHERE condition dicts for post-join filtering
            "order_by":         tuple or None
            "limit":            int or None
            "distinct":         bool
        }
    """

    VALID_JOIN_TYPES = {"INNER", "LEFT", "RIGHT", "FULL", "CROSS"}

    @staticmethod
    def build(join: dict, selected_columns: list, conditions: list,
              order_by, limit, distinct: bool) -> dict:
        """
        Validate the join descriptor and return a complete query plan.

        join is the dict produced by cli._parse_join and contains:
            join_type, left_table, right_table, left_alias, right_alias,
            on_left, on_right

        Raises ValueError if the join type is unknown or if a non-CROSS join
        is missing its ON clause.
        """
        join_type = join.get("join_type", "INNER").upper()

        if join_type not in QueryPlanner.VALID_JOIN_TYPES:
            raise ValueError(
                f"Unknown join type '{join_type}'. "
                f"Supported: {', '.join(QueryPlanner.VALID_JOIN_TYPES)}."
            )

        if join_type != "CROSS":
            if not join.get("on_left") or not join.get("on_right"):
                raise ValueError(
                    f"{join_type} JOIN requires an ON clause specifying "
                    f"the join columns from each table."
                )

        return {
            "join_type":        join_type,
            "left_table":       join["left_table"],
            "right_table":      join["right_table"],
            "left_alias":       join.get("left_alias"),
            "right_alias":      join.get("right_alias"),
            "on_left":          join.get("on_left"),
            "on_right":         join.get("on_right"),
            "selected_columns": selected_columns,
            "conditions":       conditions,
            "order_by":         order_by,
            "limit":            limit,
            "distinct":         distinct,
        }
