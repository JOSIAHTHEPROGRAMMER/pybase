def _has_aggregate(selected_columns: list) -> bool:
    agg_funcs = ("COUNT(", "SUM(", "AVG(", "MIN(", "MAX(")
    return any(
        col.upper().startswith(agg_funcs)
        for col in selected_columns
    )