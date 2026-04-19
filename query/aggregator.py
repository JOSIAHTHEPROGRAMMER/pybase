class Aggregator:
    """
    Handles GROUP BY, aggregate functions, and HAVING filtering.

    This module is intentionally isolated from Table to keep concerns clean.
    """

    @staticmethod
    def group_rows(rows: list, group_by: list, column_index: dict) -> dict:
        """
        Group rows by the given columns.

        Returns:
            {
                (group_key_tuple): [rows...]
            }
        """
        groups = {}

        for row in rows:
            key = tuple(row[column_index[col]] for col in group_by)
            groups.setdefault(key, []).append(row)

        return groups

    @staticmethod
    def apply_aggregates(groups: dict, aggregates: list,
                         column_index: dict) -> list:
        """
        Apply aggregate functions to each group.

        aggregates format:
            [{"func": "count", "column": "id"}, ...]

        Returns:
            list of result rows
        """
        results = []

        for key, rows in groups.items():
            result_row = list(key)

            for agg in aggregates:
                func = agg["func"]
                col  = agg["column"]

                if col == "*":
                    values = rows
                else:
                    idx    = column_index[col]
                    values = [r[idx] for r in rows]

                if func == "count":
                    result = len(values)

                elif func == "sum":
                    result = sum(v for v in values if v is not None)

                elif func == "avg":
                    nums = [v for v in values if v is not None]
                    result = sum(nums) / len(nums) if nums else None

                elif func == "min":
                    nums = [v for v in values if v is not None]
                    result = min(nums) if nums else None

                elif func == "max":
                    nums = [v for v in values if v is not None]
                    result = max(nums) if nums else None

                else:
                    raise ValueError(f"Unknown aggregate function '{func}'.")

                result_row.append(result)

            results.append(result_row)

        return results

    @staticmethod
    def apply_having(rows: list, having_conditions: list,
                     column_index: dict) -> list:
        """
        Filter aggregated rows using HAVING conditions.
        Uses Expression.evaluate just like WHERE.
        """
        from query.expression import Expression

        if not having_conditions:
            return rows

        filtered = []

        for row in rows:
            if all(Expression.evaluate(cond, row, column_index)
                   for cond in having_conditions):
                filtered.append(row)

        return filtered